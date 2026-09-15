"""Callback functions & State info for Sewing Pattern Configurator """

# NOTE: NiceGUI reference: https://nicegui.io/

import yaml
import traceback
from datetime import datetime
from argparse import Namespace
import numpy as np
import shutil
from pathlib import Path
import time

from nicegui import ui, app, events, background_tasks

# Async execution of regular functions
from concurrent.futures import ThreadPoolExecutor
import asyncio

# Custom
import seweasy as pyg
from .gui_pattern import GUIPattern
from . import theme
from .browser_drape import BrowserDrape, prepare_scene, snapshot_scene
from .pattern_canvas import PatternCanvas, FabricPanel
from webapp import gui_widgets as account_widgets

# Optional AI photo-to-design service (see chatgarment_modal.py); the GUI
# works without it — the feature's UI simply doesn't appear
try:
    import chatgarment_modal
except ImportError:
    chatgarment_modal = None


icon_github = """
    <svg viewbox="0 0 98 96" xmlns="http://www.w3.org/2000/svg">
    <path fill-rule="evenodd" clip-rule="evenodd" d="M48.854 0C21.839 0 0 22 0 49.217c0 
    21.756 13.993 40.172 33.405 46.69 2.427.49 3.316-1.059 3.316-2.362 
    0-1.141-.08-5.052-.08-9.127-13.59 2.934-16.42-5.867-16.42-5.867-2.184-5.704-5.42-7.17-5.42-7.17-4.448-3.015.324-3.015.324-3.015 
    4.934.326 7.523 5.052 7.523 5.052 4.367 7.496 11.404 5.378 14.235 4.074.404-3.178 1.699-5.378 3.074-6.6-10.839-1.141-22.243-5.378-22.243-24.283 
    0-5.378 1.94-9.778 5.014-13.2-.485-1.222-2.184-6.275.486-13.038 0 0 4.125-1.304 13.426 5.052a46.97 46.97 0 0 1 12.214-1.63c4.125 0 8.33.571 
    12.213 1.63 9.302-6.356 13.427-5.052 13.427-5.052 2.67 6.763.97 11.816.485 13.038 3.155 3.422 5.015 7.822 5.015 
    13.2 0 18.905-11.404 23.06-22.324 24.283 1.78 1.548 3.316 4.481 3.316 9.126 0 6.6-.08 11.897-.08 13.526 0 1.304.89 
    2.853 3.316 2.364 19.412-6.52 33.405-24.935 33.405-46.691C97.707 22 75.788 0 48.854 0z" fill="#fff"/>
    </svg>
    """
icon_arxiv = """<svg id="primary_logo_-_single_color_-_white" data-name="primary logo - single color - white" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 246.978 110.119"><path d="M492.976,269.5l24.36-29.89c1.492-1.989,2.2-3.03,1.492-4.723a5.142,5.142,0,0,0-4.481-3.161h0a4.024,4.024,0,0,0-3.008,1.108L485.2,261.094Z" transform="translate(-358.165 -223.27)" fill="#fff"/><path d="M526.273,325.341,493.91,287.058l-.972,1.033-7.789-9.214-7.743-9.357-4.695,5.076a4.769,4.769,0,0,0,.015,6.53L520.512,332.2a3.913,3.913,0,0,0,3.137,1.192,4.394,4.394,0,0,0,4.027-2.818C528.4,328.844,527.6,327.133,526.273,325.341Z" transform="translate(-358.165 -223.27)" fill="#fff"/><path d="M479.215,288.087l6.052,6.485L458.714,322.7a2.98,2.98,0,0,1-2.275,1.194,3.449,3.449,0,0,1-3.241-2.144c-.513-1.231.166-3.15,1.122-4.168l.023-.024.021-.026,24.851-29.448m-.047-1.882-25.76,30.524c-1.286,1.372-2.084,3.777-1.365,5.5a4.705,4.705,0,0,0,4.4,2.914,4.191,4.191,0,0,0,3.161-1.563l27.382-29.007-7.814-8.372Z" transform="translate(-358.165 -223.27)" fill="#fff"/><path d="M427.571,255.154c1.859,0,3.1,1.24,3.985,3.453,1.062-2.213,2.568-3.453,4.694-3.453h14.878a4.062,4.062,0,0,1,4.074,4.074v7.828c0,2.656-1.327,4.074-4.074,4.074-2.656,0-4.074-1.418-4.074-4.074V263.3H436.515a2.411,2.411,0,0,0-2.656,2.745v27.188h10.007c2.658,0,4.074,1.329,4.074,4.074s-1.416,4.074-4.074,4.074h-26.39c-2.659,0-3.986-1.328-3.986-4.074s1.327-4.074,3.986-4.074h8.236V263.3h-7.263c-2.656,0-3.985-1.329-3.985-4.074,0-2.658,1.329-4.074,3.985-4.074Z" transform="translate(-358.165 -223.27)" fill="#fff"/><path d="M539.233,255.154c2.656,0,4.074,1.416,4.074,4.074v34.007h10.1c2.746,0,4.074,1.329,4.074,4.074s-1.328,4.074-4.074,4.074H524.8c-2.656,0-4.074-1.328-4.074-4.074s1.418-4.074,4.074-4.074h10.362V263.3h-8.533c-2.744,0-4.073-1.329-4.073-4.074,0-2.658,1.329-4.074,4.073-4.074Zm4.22-17.615a5.859,5.859,0,1,1-5.819-5.819A5.9,5.9,0,0,1,543.453,237.539Z" transform="translate(-358.165 -223.27)" fill="#fff"/><path d="M605.143,259.228a4.589,4.589,0,0,1-.267,1.594L590,298.9a3.722,3.722,0,0,1-3.721,2.48h-5.933a3.689,3.689,0,0,1-3.808-2.48l-15.055-38.081a3.23,3.23,0,0,1-.355-1.594,4.084,4.084,0,0,1,4.164-4.074,3.8,3.8,0,0,1,3.718,2.656l14.348,36.134,13.9-36.134a3.8,3.8,0,0,1,3.72-2.656A4.084,4.084,0,0,1,605.143,259.228Z" transform="translate(-358.165 -223.27)" fill="#fff"/><path d="M390.61,255.154c5.018,0,8.206,3.312,8.206,8.4v37.831H363.308a4.813,4.813,0,0,1-5.143-4.929V283.427a8.256,8.256,0,0,1,7-8.148l25.507-3.572v-8.4H362.306a4.014,4.014,0,0,1-4.141-4.074c0-2.87,2.143-4.074,4.355-4.074Zm.059,38.081V279.942l-24.354,3.4v9.9Z" transform="translate(-358.165 -223.27)" fill="#fff"/><path d="M448.538,224.52h.077c1,.024,2.236,1.245,2.589,1.669l.023.028.024.026,46.664,50.433a3.173,3.173,0,0,1-.034,4.336l-4.893,5.2-6.876-8.134L446.652,230.4c-1.508-2.166-1.617-2.836-1.191-3.858a3.353,3.353,0,0,1,3.077-2.02m0-1.25a4.606,4.606,0,0,0-4.231,2.789c-.705,1.692-.2,2.88,1.349,5.1l39.493,47.722,7.789,9.214,5.853-6.221a4.417,4.417,0,0,0,.042-6.042L452.169,225.4s-1.713-2.08-3.524-2.124Z" transform="translate(-358.165 -223.27)" fill="#fff"/></svg>"""

theme_colors = theme.colors

# How the display body's baked muslin actually renders on the 3D stage
# (body colors are kept in display space; display_to_base_rgba converts
# them to material factors at export time)
DEFAULT_BODY_COLOR = '#f9f2e4'

# Static mounts are app-wide: registering them per connection only bloats
# the router. Session-specific files under /geo get unique names, so long
# browser caching is safe everywhere.
PATH_STATIC_IMG = '/img'
LOCAL_PATH_3D = Path('./tmp_gui/garm_3d')
LOCAL_PATH_3D.mkdir(parents=True, exist_ok=True)
app.add_static_files(PATH_STATIC_IMG, './assets/img', max_cache_age=24 * 3600)
app.add_static_files('/geo', LOCAL_PATH_3D, max_cache_age=30 * 24 * 3600)
app.add_static_files('/body', './assets/bodies', max_cache_age=24 * 3600)


# State of GUI
class GUIState:
    """State of GUI-related objects
    
        NOTE: "#" is used as a separator in GUI keys to avoid confusion with
            symbols that can be (typically) used in body/design parameter names 
            ('_', '-', etc.) 

    """
    def __init__(self, user=None) -> None:
        self.window = None
        self.user = user  # Signed-in account ({email, name, picture}) or None

        # Pattern: drafting is deferred (see initial_draft) so the page
        # renders instantly and the heavy assembly runs off the event loop
        self.pattern_state = GUIPattern(draft=False)

        # Paths setup (static mounts are registered once at module scope)
        self.path_static_img = PATH_STATIC_IMG
        self.body_color = DEFAULT_BODY_COLOR
        self.local_path_3d = LOCAL_PATH_3D / self.pattern_state.id
        self._view_3d_active = False
        self._preview_revision = 0
        self._prepared_revision = -1
        self._draft_pending = 1
        self._draft_failed = False
        self._preparing_3d = False
        self._released = False

        # A design stashed before an auth/account navigation survives the
        # round trip (signing in must not discard the work being saved)
        self._restored_skin = None
        self._restore_pending_design()

        # Elements
        self.ui_design_subtabs = {}
        self.ui_pattern_display = None
        self._async_executor = ThreadPoolExecutor(1)
        self._preview_executor = ThreadPoolExecutor(1)
        self._fabric_edit_lock = asyncio.Lock()

        self.stylings()
        self.layout()
        self.update_pattern_display()  # Empty until the initial draft lands

    def release(self):
        """Clean-up after the sesssion"""
        self._released = True
        # A disconnect must not remove files under an in-flight CPU mesh job.
        self._async_executor.submit(self._preview_executor.shutdown, wait=True)
        self._async_executor.submit(self._release_files)
        self._async_executor.shutdown(wait=False)

    def _release_files(self):
        self.pattern_state.release()
        if self.local_path_3d.resolve().parent == LOCAL_PATH_3D.resolve():
            shutil.rmtree(self.local_path_3d, ignore_errors=True)

    async def initial_draft(self):
        """Draft and show the starting garment; call once the page is
        delivered, so the first paint never waits on pattern assembly"""
        try:
            await asyncio.get_event_loop().run_in_executor(
                self._async_executor, self._sync_update_state)
        except Exception:
            traceback.print_exc()
            self._draft_failed = True
            self.ui_browser_drape.configure(preparing=False, error='Could not draft the starting design. Adjust its parameters to try again.')
            return
        finally:
            self._draft_pending -= 1
        if self._restored_skin:
            await self.apply_skin_color(self._restored_skin)
        self.refresh_wardrobe()
        await self.update_3d_scene()

    # --- Design persistence across navigation ---

    def stash_pending_design(self):
        """Snapshot the working design into the user's browser storage so
        a sign-in redirect or an account-page visit doesn't discard it"""
        try:
            from webapp.designs import snapshot_design_params
            from webapp.profiles import measurements_from_body
            self.pattern_state.sync_outfit_garment()
            app.storage.user['pending_design'] = {
                'design': snapshot_design_params(self.pattern_state.design_params),
                'body': measurements_from_body(self.pattern_state.body_params),
                'fabric': self.pattern_state.fabric_color,
                'outfit': snapshot_design_params(self.pattern_state.outfit_items),
                'outfit_name': getattr(self, '_outfit_name', 'Untitled outfit'),
                'active_garment': self.pattern_state.active_garment,
                'appearance': self.pattern_state.garment_appearance(),
                'skin': self.body_color
                        if self.body_color != DEFAULT_BODY_COLOR else None,
            }
        except Exception:
            traceback.print_exc()   # never block navigation on a stash failure

    def _restore_pending_design(self):
        """One-shot restore of a stashed design (see stash_pending_design)"""
        try:
            snapshot = app.storage.user.pop('pending_design', None)
        except Exception:
            snapshot = None
        if not snapshot:
            return
        try:
            self._outfit_name = snapshot.get('outfit_name', 'Untitled outfit')
            if snapshot.get('outfit'):
                self.pattern_state.load_outfit(snapshot['outfit'], snapshot.get('active_garment', 0))
            if snapshot.get('design'):
                self.pattern_state.set_new_design(snapshot['design'])
            if snapshot.get('body'):
                self.pattern_state.set_new_body_params(snapshot['body'])
            if snapshot.get('fabric'):
                self.pattern_state.fabric_color = snapshot['fabric']
            if snapshot.get('appearance'):
                self.pattern_state.panel_colors = snapshot['appearance'].get('panel_colors', {})
                self.pattern_state.panel_fabrics = snapshot['appearance'].get('panel_fabrics', {})
                self.pattern_state.panel_stiffness = snapshot['appearance'].get('panel_stiffness', {})
                self.pattern_state.panel_materials = snapshot['appearance'].get('panel_materials', {})
            self._restored_skin = snapshot.get('skin')
        except Exception:
            traceback.print_exc()   # a broken snapshot falls back to defaults

    # Initial definitions
    def stylings(self):
        """Theme definition"""
        ui.add_head_html(theme.HEAD_HTML)
        ui.add_css(Path(__file__).with_name('studio.css').read_text())
        # Theme
        # Here: https://quasar.dev/style/theme-builder
        ui.colors(
            primary=theme_colors.primary,  
            secondary=theme_colors.secondary,
            accent=theme_colors.accent,
            dark=theme_colors.dark,
            positive=theme_colors.positive,
            negative=theme_colors.negative,
            info=theme_colors.info,
            warning=theme_colors.warning
        )

    # SECTION Top level layout        
    def layout(self):
        """Pattern-first studio: wardrobe, canvas and a persistent inspector."""
        self.def_pattern_waiting()
        self.def_design_file_dialog()
        self.def_body_file_dialog()
        self.def_photo_dialog()
        self.ui_active_body_refs = {}
        self.ui_passive_body_refs = {}
        with ui.dialog().props('position=left') as self.ui_design_settings:
            with ui.card().classes('se-design-dialog'):
                with ui.row().classes('w-full items-center justify-between'):
                    ui.label('Garment design').classes('text-lg font-semibold')
                    ui.button(icon='close', on_click=self.ui_design_settings.close).props(
                        'flat round dense aria-label="Close garment design"')
                self.def_design_block()
        with ui.dialog() as self.ui_measurements_dialog:
            with ui.card().classes('w-96 max-w-full gap-3'):
                with ui.row().classes('w-full items-center justify-between'):
                    ui.label('Measurements').classes('text-lg font-semibold')
                    ui.button(icon='close', on_click=self.ui_measurements_dialog.close).props(
                        'flat round dense aria-label="Close measurements"')
                account_widgets.body_source_ui(self)

        with ui.element('main').classes('se-studio'):
            with ui.element('header').classes('se-studio-header'):
                with ui.row(wrap=False).classes('items-center gap-3 min-w-0'):
                    ui.button(icon='menu', on_click=self.toggle_wardrobe).props(
                        'flat round dense aria-label="Toggle outfit list"').classes('se-mobile-menu')
                    ui.label('SewEasy').classes('se-wordmark')
                    self.ui_outfit_title = ui.button('Untitled outfit', on_click=lambda: self.show_outfits()) \
                        .props('flat icon-right=expand_more').classes('se-outfit-title')
                with ui.row(wrap=False).classes('se-header-actions items-center gap-2'):
                    self.ui_draft_status = ui.label('Drafting…').classes('se-draft-status')
                    ui.button('Measurements', icon='straighten', on_click=self.ui_measurements_dialog.open) \
                        .props('flat').classes('se-measurements-button')
                    ui.button('Save outfit', on_click=lambda: self.show_save_outfit()) \
                        .props('unelevated').classes('se-save-outfit')
                    ui.button('Export', icon='file_download', on_click=self.state_download).props('outline')
                    with ui.element('div').classes('se-studio-account'):
                        account_widgets.auth_header_ui(self, compact=True)
            with ui.element('div').classes('se-studio-body') as self.ui_studio_body:
                with ui.element('aside').classes('se-wardrobe').props('aria-label="This outfit"'):
                    self.def_side_panel()
                self.view_stage()

        from webapp.wardrobe_ui import wardrobe_ui
        wardrobe_ui(self)

    def toggle_wardrobe(self):
        self.ui_studio_body.classes(toggle='se-wardrobe-open')

    def view_stage(self):
        """The same live GPU canvas moves between its dock and the main stage."""
        with ui.element('section').classes('se-studio-stage').props('aria-label="Pattern studio"') as self.ui_stage:
            with ui.row(wrap=False).classes('se-stage-toolbar'):
                with ui.row(wrap=False).classes('se-view-controls'):
                    self.ui_view_toggle = ui.toggle({'Sewing pattern': 'Pattern', '3D view': '3D'},
                        value='Sewing pattern', on_change=lambda e: self.switch_view(e.value)) \
                        .props('no-caps unelevated toggle-color=primary').classes('se-view-toggle')
                    self.ui_preview_status = ui.label('Preparing 3D').classes('se-preview-status').props('role=status')
                ui.button(icon='tune', on_click=self.ui_design_settings.open).props(
                    'flat dense round aria-label="Garment design settings"').classes('se-design-shortcut').tooltip('Garment design')
            with ui.element('div').classes('se-main-pattern') as self.ui_pattern_stage:
                self.def_pattern_display()
            with ui.element('div').classes('se-studio-inspector'):
                self.ui_fabric_panel = FabricPanel()
                self.ui_fabric_panel.configure(docked=True)
                self.ui_fabric_panel.on('close', self.close_fabric_panel)
                self.ui_fabric_panel.on('clear', lambda: self.set_pattern_selection([]))
                self.ui_fabric_panel.on('select-all', lambda: self.set_pattern_selection(list(self.pattern_state.panel_svg_paths)))
                self.ui_fabric_panel.on('edit', self.edit_selected_fabric)
            with ui.element('section').classes('se-preview-dock').props('aria-label="3D preview"') as self.ui_drape_stage:
                with ui.row(wrap=False).classes('se-preview-header'):
                    ui.label('3D preview').classes('font-semibold')
                    ui.space()
                    self.ui_expand_preview = ui.button(icon='open_in_full', on_click=self.expand_preview) \
                        .props('flat round dense aria-label="Expand 3D preview"').tooltip('Expand 3D preview')
                with ui.element('div').classes('se-preview-canvas'):
                    self.def_3d_scene()

    async def switch_view(self, value):
        self._view_3d_active = value == '3D view'
        self.ui_stage.classes('se-expanded-3d' if self._view_3d_active else '',
                              remove='' if self._view_3d_active else 'se-expanded-3d')
        self.ui_pattern_stage.props('inert aria-hidden=true' if self._view_3d_active else 'aria-hidden=false',
                                    remove='' if self._view_3d_active else 'inert')
        self.ui_expand_preview.props(f'icon={"close_fullscreen" if self._view_3d_active else "open_in_full"} '
            f'aria-label="{"Dock 3D preview" if self._view_3d_active else "Expand 3D preview"}"')
        self.ui_browser_drape.configure(active=self._view_3d_active, docked=not self._view_3d_active)
        await self.update_3d_scene()

    def expand_preview(self):
        self.ui_view_toggle.set_value('Sewing pattern' if self._view_3d_active else '3D view')

    def def_side_panel(self):
        with ui.row(wrap=False).classes('se-wardrobe-heading'):
            ui.label('This outfit').classes('font-semibold text-base')
            ui.space()
            ui.button(icon='close', on_click=self.toggle_wardrobe).props(
                'flat round dense aria-label="Close outfit list"').classes('se-mobile-menu')
        self.ui_outfit_list = ui.column().classes('se-outfit-list')
        ui.button('Add garment', icon='add', on_click=lambda: self.show_add_garment()) \
            .props('flat').classes('se-add-garment')
        ui.space()
        with ui.column().classes('se-wardrobe-footer'):
            ui.button('Saved outfits', icon='folder_open', on_click=lambda: self.show_outfits()).props('flat')
            with ui.button('Help & resources', icon='help_outline').props('flat size=sm'):
                with ui.menu():
                    ui.menu_item('About GarmentCode', lambda: ui.navigate.to('https://igl.ethz.ch/projects/garmentcode/', new_tab=True))
                    ui.menu_item('Source on GitHub', lambda: ui.navigate.to('https://github.com/thomashayama/SewEasy', new_tab=True))
            ui.link('Built on GarmentCode', 'https://github.com/maria-korosteleva/GarmentCode', new_tab=True) \
                .classes('se-attribution')

    def def_flat_design_subtab(self, ui_elems, design_params, use_collapsible=False):
        """Group of design parameters"""
        for param in design_params: 
            param_name = param.replace('_', ' ').capitalize()
            if 'v' not in design_params[param]:
                ui_elems[param] = {}
                if use_collapsible:
                    with ui.expansion().classes('w-full p-0 m-0') as expansion:
                        with expansion.add_slot('header'):
                            ui.label(f'{param_name}').classes('se-section-label self-center w-full h-full p-0 m-0')
                        with ui.row().classes('w-full h-full p-0 m-0'):  # Ensures correct application of style classes for children
                            self.def_flat_design_subtab(ui_elems[param], design_params[param])
                else:
                    with ui.card().classes('w-full se-stitch-card m-0'):
                        ui.label(f'{param_name}').classes('se-section-label self-center w-full h-full p-0 m-0')
                        self.def_flat_design_subtab(ui_elems[param], design_params[param])
            else:
                # Leaf value
                p_type = design_params[param]['type']
                val = design_params[param]['v']
                # range is optional (e.g. 'color' params have none); only
                # select/float/int use it, and those always provide it
                p_range = design_params[param].get('range')
                if 'select' in p_type:
                    values = design_params[param]['range']
                    if 'null' in p_type and None not in values: 
                        values.append(None)  # NOTE: Displayable value
                    ui.label(param_name).classes('p-0 m-0 mt-2 se-param-label')
                    ui_elems[param] = ui.select(
                        values, value=val,
                        on_change=lambda e, dic=design_params, param=param: self.design_param_change(dic, param, e.value)
                    ).classes('w-full').props('outlined dense options-dense')
                elif p_type == 'bool':
                    ui_elems[param] = ui.switch(
                        param_name, value=val, 
                        on_change=lambda e, dic=design_params, param=param: self.design_param_change(dic, param, e.value)
                    ).classes('text-stone-500')
                elif p_type == 'float' or p_type == 'int':
                    ui.label(param_name).classes('p-0 m-0 mt-2 se-param-label')
                    ui_elems[param] = ui.slider(
                        value=val, 
                        min=p_range[0], 
                        max=p_range[1], 
                        step=0.025 if p_type == 'float' else 1,
                    ).props('snap label').classes('w-full')  \
                        .on('change',
                            lambda e, dic=design_params, param=param: self.design_param_change(dic, param, e.args))

                    # NOTE 'change' fires when the user releases the slider:
                    # one draft per adjustment instead of one per drag tick
                    # (the 'label' prop still shows the live value while dragging)
                elif p_type == 'color':
                    ui.label(param_name).classes('p-0 m-0 mt-2 se-param-label')
                    ui_elems[param] = ui.color_input(
                        value=val,
                        on_change=lambda e, dic=design_params, param=param: self.design_param_change(dic, param, e.value)
                    ).classes('w-full').props('outlined dense')
                elif 'file' in p_type:
                    print(f'GUI::NotImplementedERROR::{param}::'
                          '"file" parameter type is not yet supported in Web SewEasy. '
                          'Creation of corresponding UI element skipped'
                    )
                else:
                    print(f'GUI::WARNING::Unknown parameter type: {p_type}')
                    ui_elems[param] = ui.input(label=param_name, value=val, placeholder='Type the value',
                        validation={'Input too long': lambda value: len(value) < 20},
                        on_change=lambda e, dic=design_params, param=param: self.design_param_change(dic, param, e.value)
                    ).classes('w-full').props('outlined dense')
                
    # Which design sections a given bottom-garment choice reads
    BASE_SECTIONS = {
        'SkirtCircle': {'flare-skirt'},
        'AsymmSkirtCircle': {'flare-skirt'},
        'SkirtManyPanels': {'flare-skirt'},
        'PencilSkirt': {'pencil-skirt'},
        'Skirt2': {'skirt'},
        'Pants': {'pants'},
    }
    SECTION_LABELS = {
        'waistband': 'Waistband', 'shirt': 'Shirt', 'collar': 'Collar',
        'sleeve': 'Sleeves', 'left': 'Asymmetry (left/right)',
        'skirt': 'Skirt', 'flare-skirt': 'Circle skirt',
        'godet-skirt': 'Godet skirt', 'pencil-skirt': 'Pencil skirt',
        'levels-skirt': 'Levels skirt', 'pants': 'Pants',
        'dress_shirt': 'Dress shirt', 'buttons': 'Buttons',
        'element_top': 'Tube top', 'fabric': 'Fabric',
    }
    META_LABELS = {'upper': 'Top', 'wb': 'Waistband', 'bottom': 'Bottom'}

    def def_design_block(self):
        """Garment composition first, then only the relevant parameter
        sections as expansions"""
        design_params = self.pattern_state.design_params
        self.ui_design_refs = {}
        self.ui_design_sections = {}

        if not self.pattern_state.is_design_sectioned():
            # Simplified display of un-sectioned design files
            self.def_flat_design_subtab(
                self.ui_design_refs, design_params, use_collapsible=True)
            return

        # The core design choice: what garments make up the outfit
        self.ui_design_refs['meta'] = {}
        meta = design_params['meta']
        for param in meta:
            values = meta[param]['range']
            if 'null' in meta[param]['type'] and None not in values:
                values.append(None)  # NOTE: Displayable value
            ui.label(self.META_LABELS.get(param, param.capitalize())) \
                .classes('p-0 m-0 mt-1 se-param-label')
            self.ui_design_refs['meta'][param] = ui.select(
                values, value=meta[param]['v'],
                on_change=lambda e, dic=meta, param=param: self.design_param_change(dic, param, e.value)
            ).classes('w-full').props('outlined dense options-dense')

        # Design-level actions
        with ui.row().classes('gap-2 mt-2'):
            ui.button('Random', on_click=self.random).props('outline size=sm icon=shuffle')
            ui.button('Default', on_click=self.default).props('outline size=sm icon=restart_alt')
            ui.button('Upload', on_click=self.ui_design_dialog.open).props('outline size=sm icon=upload_file')
            if chatgarment_modal is not None and chatgarment_modal.is_enabled():
                ui.button('From photo', on_click=self.ui_photo_dialog.open) \
                    .props('outline size=sm icon=auto_awesome') \
                    .tooltip('AI: estimate this design from a garment photo')
            # Restores the design Random/Default just replaced
            self._design_undo = None
            self.ui_undo_design_btn = ui.button('Undo', on_click=self.undo_design) \
                .props('outline size=sm icon=undo') \
                .tooltip('Restore the design that was just replaced')
            self.ui_undo_design_btn.set_visibility(False)
            ui.button('Save garment', on_click=lambda: self.show_save_garment()).props('outline size=sm icon=bookmark_add')

        # Parameter sections -- only those the current composition reads
        # are visible (see _refresh_section_relevance)
        with ui.column().classes('w-full gap-2 mt-3'):
            for section in design_params:
                if section in ('meta', 'fabric'):
                    continue
                expansion = ui.expansion(
                    self.SECTION_LABELS.get(section, section)
                ).classes('w-full se-stitch-card')
                with expansion:
                    self.ui_design_refs[section] = {}
                    self.def_flat_design_subtab(
                        self.ui_design_refs[section],
                        design_params[section],
                        use_collapsible=(section == 'left')
                    )
                self.ui_design_sections[section] = expansion
        self._refresh_section_relevance()

    def _relevant_sections(self):
        """Design sections that the currently chosen garments actually use"""
        design = self.pattern_state.design_params
        upper = design['meta']['upper']['v']
        wb = design['meta']['wb']['v']
        bottom = design['meta']['bottom']['v']

        relevant = set()  # Fabric editing lives beside the pattern canvas.
        if upper == 'DressShirt':
            # Self-contained: own section + sleeves + buttons (no generic
            # collar/asym)
            relevant |= {'dress_shirt', 'sleeve', 'buttons'}
        elif upper == 'ElementTubeTop':
            # Self-contained strapless top: only its own section (no sleeves,
            # collar, buttons or asymmetry)
            relevant |= {'element_top'}
        elif upper:
            relevant |= {'shirt', 'collar', 'sleeve', 'left'}
        if wb:
            relevant.add('waistband')
        relevant |= self.BASE_SECTIONS.get(bottom, set())
        if bottom == 'GodetSkirt':
            relevant.add('godet-skirt')
            relevant |= self.BASE_SECTIONS.get(design['godet-skirt']['base']['v'], set())
        if bottom == 'SkirtLevels':
            relevant.add('levels-skirt')
            relevant |= self.BASE_SECTIONS.get(design['levels-skirt']['base']['v'], set())
        return relevant

    def _refresh_section_relevance(self):
        """Show only the parameter sections relevant to the current garments"""
        if not getattr(self, 'ui_design_sections', None):
            return
        relevant = self._relevant_sections()
        for section, expansion in self.ui_design_sections.items():
            expansion.set_visibility(section in relevant)
                            
    # !SECTION
    # SECTION -- Pattern visuals
    def def_pattern_display(self):
        self.selected_panels = []
        with ui.element('div').classes('se-pattern-layout'):
            with ui.element('div').classes('se-pattern-sheet'):
                with ui.element('div').classes('se-workspace w-full h-full').props(
                        'tabindex="0" aria-label="Sewing pattern workspace"'), ui.element('div').classes(
                        'se-pattern-paper').style('width:1000px') as self.ui_pattern_bg:
                    self.ui_pattern_display = PatternCanvas().classes('bg-transparent p-0 m-0')
                    self.ui_pattern_display.on('selection', self.on_pattern_selection)
                with ui.row(wrap=False).classes('se-pattern-tools'):
                    ui.button(icon='remove', on_click=lambda: self.ui_pattern_display.run_method('zoom', 1 / 1.2)) \
                        .props('flat dense round aria-label="Zoom out pattern"')
                    ui.button('Fit', on_click=lambda: self.ui_pattern_display.run_method('fit')) \
                        .props('flat dense aria-label="Fit pattern to view"')
                    ui.button(icon='add', on_click=lambda: self.ui_pattern_display.run_method('zoom', 1.2)) \
                        .props('flat dense round aria-label="Zoom in pattern"')
                with ui.column().classes('se-pattern-options'):
                    self.ui_self_intersect = ui.label('Panels overlap in this design').classes('se-warning-chip') \
                        .bind_visibility(self.pattern_state, 'is_self_intersecting')
                ui.label('Drag to select • Shift/Ctrl to add').classes('se-canvas-hint')

    def def_3d_scene(self):
        self.ui_browser_drape = BrowserDrape(self.pattern_state.fabric_color, self.body_color) \
            .classes('w-full h-full p-0 m-0')
        self.ui_browser_drape.configure(docked=True)
        self.ui_browser_drape.on('retry', self.retry_3d_scene)
        self.ui_browser_drape.on('show-body', lambda e: self.ui_browser_drape.configure(show_body=e.args['value']))
        self.ui_browser_drape.on('state', self.preview_state_changed)

    def preview_state_changed(self, e):
        value = e.args.get('value', 'preparing')
        self.ui_preview_status.set_text({'ready': '3D ready', 'warming': 'Settling',
            'running': 'Live 3D', 'paused': 'Paused', 'error': 'Preview unavailable',
            'empty': 'No preview'}.get(value, 'Preparing 3D'))
        self.ui_preview_status.props(f'data-state={value}')

    # !SECTION
    # SECTION -- Other UI details
    def def_pattern_waiting(self):
        """Define the waiting splashcreen with spinner
            (e.g. waiting for a pattern to update)"""

        # NOTE: the screen darkens because of the shadow
        with ui.dialog(value=False).props(
            'persistent maximized'
        ) as self.spin_dialog, ui.card().classes('bg-transparent'):
            with ui.column().classes('fixed-center items-center gap-4'):
                # Styles https://quasar.dev/vue-components/spinners
                ui.spinner('tail', size='6em', color='white')
                self.spin_message = ui.label('') \
                    .classes('text-white text-lg text-center max-w-md')

    def open_spinner(self, message=''):
        """Show the blocking spinner with a message saying what is running"""
        self.spin_message.set_text(message)
        self.spin_dialog.open()

    def def_body_file_dialog(self):
        """ Dialog for loading parameter files (body)
        """
        async def handle_upload(e: events.UploadEventArguments):
            try:
                param_dict = yaml.safe_load(e.content.read())['body']
                if not isinstance(param_dict, dict):
                    raise TypeError('"body" section is not a mapping')
            except Exception:
                traceback.print_exc()
                ui.notify('Could not read this file — expected a SewEasy '
                          'body-measurements YAML or JSON with a "body" section',
                          type='negative', close_button=True)
                return

            from webapp import measurement_guide
            errors, warnings = measurement_guide.validate_measurements(param_dict)
            if errors:
                ui.notify('File not applied — impossible measurements:\n• '
                          + '\n• '.join(errors),
                          type='negative', multi_line=True, close_button=True)
                return
            if warnings:
                ui.notify('Check these values:\n• ' + '\n• '.join(warnings),
                          type='warning', multi_line=True, close_button=True)

            self.toggle_param_update_events(self.ui_active_body_refs)
            try:
                self.pattern_state.set_new_body_params(param_dict)
                self.mark_custom_measurements()
                self.update_body_params_ui_state(self.ui_active_body_refs)
                await self.update_pattern_ui_state()
            except Exception:
                traceback.print_exc()
                ui.notify('Could not apply these measurements',
                          type='negative', close_button=True)
                return
            finally:
                self.toggle_param_update_events(self.ui_active_body_refs)

            ui.notify(f'Successfully applied {e.name}')
            self.ui_body_dialog.close()

        with ui.dialog() as self.ui_body_dialog, ui.card().classes('items-center'):
            # NOTE: https://www.reddit.com/r/nicegui/comments/1393i2f/file_upload_with_restricted_types/
            ui.upload(
                label='Body parameters .yaml or .json',  
                on_upload=handle_upload
            ).classes('max-w-full').props('accept=".yaml,.json"')  

            ui.button('Close without upload', on_click=self.ui_body_dialog.close)

    def def_design_file_dialog(self):
        """ Dialog for loading parameter files (design)
        """

        async def handle_upload(e: events.UploadEventArguments):
            try:
                param_dict = yaml.safe_load(e.content.read())['design']
                if not isinstance(param_dict, dict):
                    raise TypeError('"design" section is not a mapping')
            except Exception:
                traceback.print_exc()
                ui.notify('Could not read this file — expected a SewEasy '
                          'design YAML or JSON with a "design" section',
                          type='negative', close_button=True)
                return

            self.toggle_param_update_events(self.ui_design_refs)  # Don't react to value updates
            try:
                self.pattern_state.set_new_design(param_dict)
                self.update_design_params_ui_state(self.ui_design_refs, self.pattern_state.design_params)
                await self.update_pattern_ui_state()
            except Exception:
                traceback.print_exc()
                ui.notify('Could not apply this design file',
                          type='negative', close_button=True)
                return
            finally:
                self.toggle_param_update_events(self.ui_design_refs)  # Re-enable reaction to value updates

            ui.notify(f'Successfully applied {e.name}')
            self.ui_design_dialog.close()

        with ui.dialog() as self.ui_design_dialog, ui.card().classes('items-center'):
            # NOTE: https://www.reddit.com/r/nicegui/comments/1393i2f/file_upload_with_restricted_types/
            ui.upload(
                label='Design parameters .yaml or .json',  
                on_upload=handle_upload
            ).classes('max-w-full').props('accept=".yaml,.json"')  

            ui.button('Close without upload', on_click=self.ui_design_dialog.close)

    def def_photo_dialog(self):
        """Dialog for estimating a design from a garment photo (AI service,
        see chatgarment_modal.py)"""

        async def handle_upload(e: events.UploadEventArguments):
            img_bytes = e.content.read()
            name = e.name
            self.ui_photo_dialog.close()
            self._snapshot_design_for_undo()
            self.open_spinner('Estimating a design from your photo… '
                              'A first request can take a few minutes '
                              'while the AI model starts up')
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    self._async_executor,
                    lambda: chatgarment_modal.photo_to_design(img_bytes))
                design = chatgarment_modal.merge_designs(result['designs'])
                if design is None:
                    raise RuntimeError(result.get('error') or 'no garment recognized')
            except Exception:
                traceback.print_exc()
                self.spin_dialog.close()
                ui.notify('Could not estimate a design from this photo — '
                          'try a clearer, full-garment shot',
                          type='negative', close_button=True)
                return

            self.toggle_param_update_events(self.ui_design_refs)
            try:
                self.pattern_state.set_new_design(design)
                self.update_design_params_ui_state(
                    self.ui_design_refs, self.pattern_state.design_params)
                await self.update_pattern_ui_state()
                if result.get('error'):
                    # Some garments of the outfit made it, some didn't
                    ui.notify(f'Applied a partial result: {result["error"]}',
                              type='warning', close_button=True)
                else:
                    ui.notify(f'Design estimated from {name} — drafted '
                              'for the current body measurements',
                              type='positive')
            except Exception:
                traceback.print_exc()
                ui.notify('The estimated design could not be drafted',
                          type='negative', close_button=True)
            finally:
                self.toggle_param_update_events(self.ui_design_refs)
                self.spin_dialog.close()

        with ui.dialog() as self.ui_photo_dialog, ui.card().classes('items-center'):
            ui.label('Upload a photo of a garment. AI estimates its design, '
                     'and the pattern is drafted to the current body '
                     'measurements — not the body in the photo.') \
                .classes('max-w-xs text-center')
            ui.upload(
                label='Garment photo',
                on_upload=handle_upload,
                max_file_size=10_000_000,
                auto_upload=True,
            ).classes('max-w-full').props('accept="image/*"')

            ui.button('Close without upload', on_click=self.ui_photo_dialog.close)

    # !SECTION
    # SECTION -- Event callbacks
    def design_param_change(self, params, key, value):
        # Loading a garment updates controls programmatically. NiceGUI calls
        # their change handlers even when disabled: don't enqueue drafts for
        # values already in the model (or race them against the new garment).
        if params[key]['v'] != value:
            return self.update_pattern_ui_state(params, key, value)

    async def update_pattern_ui_state(self, param_dict=None, param=None, new_value=None, body_param=False):
        """UI was updated -- update the state of the pattern parameters and visuals"""
        # NOTE: Fixing to the "same value" issue in lambdas 
        # https://github.com/zauberzeug/nicegui/wiki/FAQs#why-have-all-my-elements-the-same-value
   
        print('INFO::Updating pattern...')
        self.ui_draft_status.set_text('Drafting…')
        self._preview_revision += 1
        self._draft_pending += 1
        self._draft_failed = True
        self.pattern_state.is_in_3D = False
        self.ui_browser_drape.configure(scene_url='', preparing=True, error='')

        # Update the values
        if param_dict is not None:
            if body_param:
                param_dict[param] = new_value
            else:
                param_dict[param]['v'] = new_value
                self.pattern_state.is_in_3D = False   # Design param changes -> 3D model is not synced with the param

        # Keep the visible parameter sections in sync with the composition
        self._refresh_section_relevance()

        # NOTE: even "quick" drafts run in the executor — pattern assembly
        # is CPU-bound Python, and NiceGUI serves every session from one
        # event loop, so a synchronous draft freezes all connected users.
        slow = self.pattern_state.is_slow_design()
        try:
            if slow:
                # Splashscreen blocks users from modifying params while updating
                # https://github.com/zauberzeug/nicegui/discussions/1988
                self.open_spinner('Updating the pattern…')

            self.loop = asyncio.get_event_loop()
            await self.loop.run_in_executor(self._async_executor, self._sync_update_state)
            self._draft_failed = False

        except Exception as e:
            traceback.print_exc()
            print(e)
            ui.notify(
                'This parameter combination could not be drafted — '
                'try different values',
                type='negative',
                close_button=True,
                position='center'
            )
            self.ui_browser_drape.configure(preparing=False, error='This design could not be drafted. Adjust its parameters to preview it.')
            return
        finally:
            self.spin_dialog.close()  # If open
            self._draft_pending -= 1
        self.refresh_wardrobe()
        background_tasks.create(self.update_3d_scene())

    def _sync_update_state(self):
        # Update derivative body values (just in case)
        # TODOLOW only do that on body value updates
        self.pattern_state.body_params.eval_dependencies()
        self.update_body_params_ui_state(self.ui_passive_body_refs) # Display evaluated dependencies

        # Update the garment
        # Sync left-right for easier editing
        self.pattern_state.sync_left(with_check=True)

        # NOTE This is the slow part 
        self.pattern_state.reload_garment()

        # Update display
        self.update_pattern_display()

    def update_pattern_display(self):
        """Display the laid-out cutting pieces without changing assembly geometry."""
        if self.ui_pattern_display is None:
            return
        if self.pattern_state.svg_filename:
            width, height = self.pattern_state.svg_bbox_size
            self.ui_pattern_display.set_source(str(self.pattern_state.svg_path()))
            self.ui_pattern_display.configure(
                viewbox=f'0 0 {width} {height}',
                pieces=[{'id': name, 'label': self.panel_label(name), 'path': path.d() + ' Z',
                         **self.pattern_state.panel_svg_labels[name]}
                        for name, path in self.pattern_state.panel_svg_paths.items()])
            self.set_pattern_selection(self.selected_panels, open_panel=False)
        else:
            self.ui_pattern_display.set_source('')
            self.ui_pattern_display.configure(pieces=[], selected=[])
            self.selected_panels = []
            self.ui_fabric_panel.configure(selection=[], available=0)

    def panel_label(self, name):
        prefix = ''
        if self.pattern_state.outfit_items and '__' in name:
            group, name = name.split('__', 1)
            item = self.pattern_state.outfit_items[int(group[1:])]
            prefix = item.get('name', 'Garment') + ' · '
        name = name.removeprefix('sl_')
        if name.endswith(('_f', '_b')):
            name = name[:-2] + ('_front' if name.endswith('_f') else '_back')
        words = name.replace('ftorso', 'front bodice').replace('btorso', 'back bodice').replace('_', ' ')
        return prefix + words[:1].upper() + words[1:]

    def on_pattern_selection(self, e):
        self.set_pattern_selection(e.args.get('panels', []))

    def close_fabric_panel(self):
        self.set_pattern_selection([], open_panel=False)
        self.ui_fabric_panel.configure(open=False)

    def set_pattern_selection(self, panels, open_panel=True):
        self.selected_panels = list(dict.fromkeys(p for p in panels if p in self.pattern_state.panel_svg_paths))
        self.ui_pattern_display.configure(selected=self.selected_panels)
        settings = self.pattern_state.panel_fabric_settings(self.selected_panels)
        self.ui_fabric_panel.configure(
            selection=[dict(id=p, label=self.panel_label(p), **settings[p]) for p in self.selected_panels],
            available=len(self.pattern_state.panel_svg_paths),
            **({'open': True} if open_panel and self.selected_panels else {}))

    async def edit_selected_fabric(self, e):
        data = e.args
        panels = [p for p in data.get('panels', []) if p in self.pattern_state.panel_svg_paths]
        if not panels:
            return
        async with self._fabric_edit_lock:
            self.ui_fabric_panel.configure(busy=True)
            try:
                await asyncio.get_running_loop().run_in_executor(
                    self._async_executor, self.pattern_state.edit_panel_fabrics,
                    panels, data.get('field'), data.get('value'))
                self.update_pattern_display()
                self.ui_browser_drape.configure(panel_colors=self.pattern_state.display_panel_colors(),
                                                panel_fabrics=self.pattern_state.display_panel_fabrics())
                if data.get('field') in ('material', 'stiffness', 'reset'):
                    self._preview_revision += 1
                    self.ui_browser_drape.configure(scene_url='')
                    background_tasks.create(self.update_3d_scene())
            except ValueError as error:
                ui.notify(str(error), type='warning')
            finally:
                self.ui_fabric_panel.configure(busy=False)
                self.refresh_wardrobe()

    def update_design_params_ui_state(self, ui_elems, design_params):
        """Sync ui params with the current state of the design params"""
        for param in design_params: 
            if param not in ui_elems:
                continue
            if 'v' not in design_params[param]:
                self.update_design_params_ui_state(ui_elems[param], design_params[param])
            else:
                ui_elems[param].value = design_params[param]['v']

    def toggle_param_update_events(self, ui_elems):
        """Enable/disable event handling on the ui elements related to SewEasy parameters"""
        for param in ui_elems:
            if isinstance(ui_elems[param], dict):
                self.toggle_param_update_events(ui_elems[param])
            else:
                if ui_elems[param].is_ignoring_events:  # -> disabled
                    ui_elems[param].enable()
                else:
                    ui_elems[param].disable()

    def update_body_params_ui_state(self, ui_body_refs):
        """Sync ui params with the current state of the body params"""
        for param in ui_body_refs: 
            ui_body_refs[param].value = self.pattern_state.body_params[param]

    async def retry_3d_scene(self):
        if self._draft_failed:
            await self.update_pattern_ui_state()
        else:
            await self.update_3d_scene()

    async def update_3d_scene(self):
        """Prepare the newest design as soon as its 2D draft is available."""
        if self._released or self._draft_pending or self._draft_failed or self._preparing_3d:
            return
        if self._prepared_revision == self._preview_revision:
            return
        self._preparing_3d = True
        try:
            while not self._released and not self._draft_pending and not self._draft_failed:
                revision = self._preview_revision
                if not self.pattern_state.svg_filename:
                    self.ui_browser_drape.configure(scene_url='', preparing=False, error='')
                    return
                self.ui_browser_drape.configure(preparing=True, error='')
                target = self.local_path_3d / f'scene-{revision}.json'
                try:
                    draft = await asyncio.get_running_loop().run_in_executor(
                        self._async_executor, snapshot_scene, self.pattern_state)
                    if self._released:
                        return
                    if revision != self._preview_revision or self._draft_pending:
                        continue
                    await asyncio.get_running_loop().run_in_executor(
                        self._preview_executor, prepare_scene, draft, target)
                except Exception:
                    traceback.print_exc()
                    if revision != self._preview_revision and not self._released:
                        continue
                    if revision == self._preview_revision and not self._released:
                        self.ui_browser_drape.configure(preparing=False,
                            error='Could not prepare this pattern for 3D. Retry or adjust the design.')
                    return
                if self._released:
                    return
                if revision != self._preview_revision:
                    target.unlink(missing_ok=True)
                    continue
                self._prepared_revision = revision
                self.ui_browser_drape.configure(
                    scene_url=f'/geo/{self.pattern_state.id}/{target.name}',
                    preparing=False, error='', fabric_color=self.pattern_state.fabric_color,
                    panel_colors=self.pattern_state.display_panel_colors(),
                    panel_fabrics=self.pattern_state.display_panel_fabrics())
                # Each revision has an immutable URL; old scenes are no longer used.
                for old in self.local_path_3d.glob('scene-*.json'):
                    if old != target:
                        old.unlink(missing_ok=True)
                return
        finally:
            self._preparing_3d = False

    async def update_fabric_color(self, color):
        """Apply a new fabric color to the 2D pattern and the draped 3D garment"""
        if not color or color == self.pattern_state.fabric_color:
            return

        print('INFO::Updating fabric color...')

        self.loop = asyncio.get_event_loop()

        # 2D: SVG re-serialization of the already-assembled pattern —
        # still an assembly+render pass, so keep it off the event loop
        await self.loop.run_in_executor(
            self._async_executor, self.pattern_state.set_fabric_color, color)
        self.update_pattern_display()

        self.ui_browser_drape.configure(fabric_color=color,
                                        panel_colors=self.pattern_state.display_panel_colors(),
                                        panel_fabrics=self.pattern_state.display_panel_fabrics())

    async def update_body_color(self, color):
        """Update the browser material without re-exporting a mannequin."""
        if not color or color == self.body_color:
            return
        self.body_color = color
        self.ui_browser_drape.configure(body_color=color)

    async def apply_skin_color(self, color):
        """Apply the profile's stored skin tone (None -> default muslin)."""
        color = color or DEFAULT_BODY_COLOR
        await self.update_body_color(color)

    def apply_fabric_color_visuals(self, color):
        """Set the fabric color state + 2D display (no 3D export) —
        used when a saved outfit restores its color"""
        if not color or color == self.pattern_state.fabric_color:
            return
        self.pattern_state.fabric_color = color
        self.ui_browser_drape.configure(fabric_color=color)

    def adopt_drape(self, glb_bytes):
        """Retain an outfit's stored export; the live preview uses its design."""
        self.pattern_state.adopt_drape_glb(glb_bytes)

    # Design buttons updates
    async def design_sample(self):
        """Run design sampling"""
        self.loop = asyncio.get_event_loop()
        # reload=False: update_pattern_ui_state drafts right after — no
        # need to assemble the garment twice per click
        await self.loop.run_in_executor(
            self._async_executor,
            lambda: self.pattern_state.sample_design(reload=False))

    def _snapshot_design_for_undo(self):
        """Remember the design about to be replaced by Random/Default"""
        from webapp.designs import snapshot_design_params
        self._design_undo = snapshot_design_params(self.pattern_state.design_params)
        self.ui_undo_design_btn.set_visibility(True)

    async def undo_design(self):
        """Bring back the design Random/Default overwrote"""
        if not self._design_undo:
            return
        params, self._design_undo = self._design_undo, None
        self.ui_undo_design_btn.set_visibility(False)
        self.toggle_param_update_events(self.ui_design_refs)
        try:
            self.pattern_state.set_new_design(params)
            self.update_design_params_ui_state(self.ui_design_refs, self.pattern_state.design_params)
            await self.update_pattern_ui_state()
        finally:
            self.toggle_param_update_events(self.ui_design_refs)

    async def random(self):
        self._snapshot_design_for_undo()
        # Sampling could be slow, so add spin always
        self.open_spinner('Sampling a random design…')

        self.toggle_param_update_events(self.ui_design_refs)  # Don't react to value updates
        try:
            await self.design_sample()
            self.update_design_params_ui_state(self.ui_design_refs, self.pattern_state.design_params)
            await self.update_pattern_ui_state()
        except Exception as e:
            traceback.print_exc()
            print(e)
            ui.notify('Random sampling failed — please try again',
                      type='negative', close_button=True)
        finally:
            # The spinner and the controls must always come back —
            # otherwise a sampling error locks the whole UI
            self.toggle_param_update_events(self.ui_design_refs)
            self.spin_dialog.close()

    async def default(self):
        self._snapshot_design_for_undo()
        self.toggle_param_update_events(self.ui_design_refs)
        try:
            self.pattern_state.restore_design(False)
            self.update_design_params_ui_state(self.ui_design_refs, self.pattern_state.design_params)
            await self.update_pattern_ui_state()
        finally:
            self.toggle_param_update_events(self.ui_design_refs)

    # !SECTION

    async def state_download(self):
        """Download the current garment as a print-ready PDF"""
        try:
            # Tiling + per-page cairosvg rendering takes seconds for a
            # complex garment: run off the loop, with visible progress
            self.open_spinner('Preparing your print-ready PDF…')
            self.loop = asyncio.get_event_loop()
            pdf_path = await self.loop.run_in_executor(
                self._async_executor, self.pattern_state.save)
        except pyg.EmptyPatternError:
            ui.notify('Nothing to print yet — choose a garment first',
                      type='warning')
            return
        except Exception as e:
            traceback.print_exc()
            print(e)
            ui.notify('Could not generate the PDF — please try again',
                      type='negative', close_button=True)
            return
        finally:
            self.spin_dialog.close()
        ui.download(pdf_path, f'SewEasy_pattern_{datetime.now().strftime("%y%m%d-%H-%M-%S")}.pdf')
        ui.notify('Your pattern PDF is downloading', type='positive')
