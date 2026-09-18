"""Mutual friend requests. Email lookup never exposes an account directory."""
import re
from uuid import uuid4

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from webapp.db import SessionLocal
from webapp.models import Friendship, User


def normalize_email(value):
    value = (value or '').strip().lower()
    if len(value) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
        raise ValueError('Enter a valid email address.')
    return value


def friend_emails(db, email):
    if not email:
        return []
    rows = db.query(Friendship).filter(
        or_(Friendship.email_a == email, Friendship.email_b == email),
        Friendship.status == 'accepted').all()
    return [r.email_b if r.email_a == email else r.email_a for r in rows]


def are_friends(db, first, second):
    if not first or not second or first == second:
        return False
    a, b = sorted((first, second))
    return db.query(Friendship.id).filter_by(email_a=a, email_b=b, status='accepted').first() is not None


class Friends:
    def __init__(self, email):
        self.email = normalize_email(email) if email else None

    def _account(self, db):
        if not self.email or db.get(User, self.email) is None:
            raise ValueError('Sign in to manage friends.')

    def list(self):
        result = dict(friends=[], incoming=[], outgoing=[])
        if not self.email:
            return result
        with SessionLocal() as db:
            rows = db.query(Friendship).filter(or_(Friendship.email_a == self.email,
                                                  Friendship.email_b == self.email)).order_by(Friendship.created_at.desc()).all()
            emails = {r.email_b if r.email_a == self.email else r.email_a for r in rows}
            people = {u.email: u for u in db.query(User).filter(User.email.in_(emails))} if emails else {}
            for row in rows:
                other = row.email_b if row.email_a == self.email else row.email_a
                group = 'friends' if row.status == 'accepted' else 'outgoing' if row.requester_email == self.email else 'incoming'
                # Outgoing requests must look identical whether an address has
                # registered or not. Identity is disclosed only after consent.
                person = people.get(other) if group != 'outgoing' else None
                result[group].append(dict(id=row.id, email=other,
                    name=person.name if person and person.name else other))
        return result

    def request(self, recipient):
        recipient = normalize_email(recipient)
        if recipient == self.email:
            raise ValueError('Choose someone other than yourself.')
        a, b = sorted((self.email or '', recipient))
        with SessionLocal() as db:
            self._account(db)
            row = db.query(Friendship).filter_by(email_a=a, email_b=b).first()
            if row:
                if row.status == 'accepted':
                    raise ValueError('You are already friends.')
                if row.requester_email != self.email:
                    raise ValueError('This person already requested to be your friend. Accept their request below.')
                return row.id
            if db.query(Friendship.id).filter_by(requester_email=self.email, status='pending').count() >= 50:
                raise ValueError('You have 50 pending requests. Cancel an older request first.')
            row = Friendship(id=uuid4().hex, email_a=a, email_b=b, requester_email=self.email, status='pending')
            db.add(row)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                raise ValueError('A request already exists. Refresh your friends list.') from None
            return row.id

    def accept(self, request_id):
        with SessionLocal() as db:
            self._account(db)
            row = db.query(Friendship).filter_by(id=request_id).with_for_update().first()
            if row is None or self.email not in (row.email_a, row.email_b) or row.requester_email == self.email:
                raise ValueError('This friend request is no longer available.')
            row.status = 'accepted'
            db.commit()

    def remove(self, request_id):
        """Cancel, decline or unfriend; never permits touching a third party pair."""
        with SessionLocal() as db:
            self._account(db)
            row = db.query(Friendship).filter_by(id=request_id).filter(
                or_(Friendship.email_a == self.email, Friendship.email_b == self.email)).with_for_update().first()
            if row is None:
                raise ValueError('This connection is no longer available.')
            db.delete(row)
            db.commit()
