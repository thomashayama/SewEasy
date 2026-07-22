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

from nicegui import ui, app, events

# Async execution of regular functions
from concurrent.futures import ThreadPoolExecutor
import asyncio

# Custom
import seweasy as pyg
from .gui_pattern import GUIPattern
from . import theme
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

# Skin tone ramp + helpers live with the rest of the body knowledge
from webapp.measurement_guide import skin_tone_hex, skin_tone_t
# Skin-tinted mannequin exports, cached by tone across sessions
from webapp import body_display

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

        # Pattern display constants
        self.canvas_aspect_ratio = 1500. / 900   # Millimiter paper
        self.w_rel_body_size = 0.5  # Body size as fraction of horisontal canvas axis
        self.h_rel_body_size = 0.95
        self.background_body_scale = 1 / 171.99   # Inverse of the mean_all body height from GGG
        self.background_body_canvas_center = 0.273  # Fraction of the canvas (millimiter paper)
        self.w_canvas_pad, self.h_canvas_pad = 0.011, 0.04
        self.body_outline_classes = ''   # Application of pattern&body scaling when it overflows

        # Paths setup (static mounts are registered once at module scope)
        self.path_static_img = PATH_STATIC_IMG
        self.garm_3d_filename = f'garm_3d_{self.pattern_state.id}.glb'
        self.body_color = DEFAULT_BODY_COLOR
        self.local_path_3d = LOCAL_PATH_3D

        # A design stashed before an auth/account navigation survives the
        # round trip (signing in must not discard the work being saved)
        self._restored_skin = None
        self._restore_pending_design()

        # Elements
        self.ui_design_subtabs = {}
        self.ui_pattern_display = None
        self._async_executor = ThreadPoolExecutor(1)

        self.stylings()
        self.layout()
        self.update_pattern_display()  # Empty until the initial draft lands

    def release(self):
        """Clean-up after the sesssion"""
        self.pattern_state.release()
        (self.local_path_3d / self.garm_3d_filename).unlink(missing_ok=True)

    async def initial_draft(self):
        """Draft and show the starting garment; call once the page is
        delivered, so the first paint never waits on pattern assembly"""
        await asyncio.get_event_loop().run_in_executor(
            self._async_executor, self._sync_update_state)
        if self._restored_skin:
            await self.apply_skin_color(self._restored_skin)

    # --- Design persistence across navigation ---

    def stash_pending_design(self):
        """Snapshot the working design into the user's browser storage so
        a sign-in redirect or an account-page visit doesn't discard it"""
        try:
            from webapp.designs import snapshot_design_params
            from webapp.profiles import measurements_from_body
            app.storage.user['pending_design'] = {
                'design': snapshot_design_params(self.pattern_state.design_params),
                'body': measurements_from_body(self.pattern_state.body_params),
                'fabric': self.pattern_state.fabric_color,
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
            if snapshot.get('design'):
                self.pattern_state.set_new_design(snapshot['design'])
            if snapshot.get('body'):
                self.pattern_state.set_new_body_params(snapshot['body'])
            if snapshot.get('fabric'):
                self.pattern_state.fabric_color = snapshot['fabric']
            self._restored_skin = snapshot.get('skin')
        except Exception:
            traceback.print_exc()   # a broken snapshot falls back to defaults

    # Initial definitions
    def stylings(self):
        """Theme definition"""
        ui.add_head_html(theme.HEAD_HTML)
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
        """Overall page layout"""

        # as % of viewport width/height
        self.h_header = 5
        self.h_params_content = 86
        self.h_garment_display = 74 
        self.w_garment_display = 65
        self.w_splitter_design = 32
        self.scene_base_resoltion = (1024, 800)

        # Helpers
        self.def_pattern_waiting()
        # TODOLOW One dialog for both? 
        self.def_design_file_dialog()
        self.def_body_file_dialog()
        self.def_photo_dialog()

        # Configurator GUI
        # Collapsible configuration side panel
        # breakpoint: below 1024px CSS width the drawer overlays the stage
        # and can be dismissed — a 390px fixed panel would swallow a phone
        # screen entirely
        self.ui_side_panel = ui.left_drawer(value=True, elevated=False, bordered=True) \
            .classes('relative px-3 py-2 bg-[#fcfcfa]').props('width=390 breakpoint=1024')
        with self.ui_side_panel:
            self.def_side_panel()

        # Full-bleed pattern/3D stage; all controls float on top
        with ui.element('div').classes(
                f'relative w-full h-[calc(100dvh-{self.h_header}vh-11px)] p-0 m-0 overflow-hidden'):
            self.view_stage()

        # Overall wrapping
        # NOTE: https://nicegui.io/documentation/section_pages_routing#page_layout
        with ui.header(elevated=False, fixed=False).classes('flex-col p-0 m-0 gap-0'):
            with ui.row(wrap=False).classes(f'w-full h-[{self.h_header}vh] items-center justify-between py-0 px-5 m-0'):
                # Brand
                with ui.row(wrap=False).classes('items-center gap-2.5'):
                    ui.button(icon='menu', on_click=self.ui_side_panel.toggle) \
                        .props('flat color=white dense round aria-label="Toggle configuration panel"') \
                        .tooltip('Configuration panel')
                    ui.icon('content_cut').classes('text-2xl rotate-[-90deg] opacity-90')
                    with ui.column().classes('gap-0.5'):
                        ui.label('SewEasy').classes('se-wordmark')
                        ui.label('parametric pattern studio').classes('se-eyebrow')
                # Links + account
                with ui.row(wrap=False).classes('items-center gap-1'):
                    with ui.button('Resources').props('flat color=white no-caps icon-right=expand_more'):
                        with ui.menu():
                            ui.menu_item(
                                'About GarmentCode',
                                lambda: ui.navigate.to('https://igl.ethz.ch/projects/garmentcode/', new_tab=True))
                            ui.menu_item(
                                'Paper (arXiv)',
                                lambda: ui.navigate.to('https://arxiv.org/abs/2306.03642', new_tab=True))
                            ui.menu_item(
                                'GarmentCodeData dataset',
                                lambda: ui.navigate.to('https://igl.ethz.ch/projects/GarmentCodeData/', new_tab=True))
                            ui.menu_item(
                                'Source on GitHub',
                                lambda: ui.navigate.to('https://github.com/thomashayama/SewEasy', new_tab=True))
                    account_widgets.auth_header_ui(self)
            # Signature: selvedge edge
            ui.element('div').classes('se-selvedge w-full')
        # NOTE No footer: attribution floats over the stage (see view_stage)

    def view_stage(self):
        """Full-bleed 2D/3D stage; the view switcher and actions float on top"""
        with ui.tabs().classes('hidden') as tabs:
            self.ui_2d_tab = ui.tab('Sewing pattern')
            self.ui_3d_tab = ui.tab('3D view')
        with ui.tab_panels(tabs, value=self.ui_2d_tab, animated=False) \
                .classes('w-full h-full p-0 m-0'):
            with ui.tab_panel(self.ui_2d_tab).classes('w-full h-full p-0 m-0 relative'):
                self.def_pattern_display()
            with ui.tab_panel(self.ui_3d_tab).classes('w-full h-full p-0 m-0 relative'):
                self.def_3d_scene()

        # Floating view switcher + fabric color picker
        with ui.row(wrap=False).classes(
                'absolute top-3 left-1/2 -translate-x-1/2 z-50 items-center gap-2'):
            ui.toggle(['Sewing pattern', '3D view'], value='Sewing pattern',
                      on_change=lambda e: tabs.set_value(e.value)) \
                .props('no-caps unelevated rounded toggle-color=primary padding="2px 14px"') \
                .classes('se-overlay-chip')

            # Fabric color: applies to both the 2D pattern and the 3D drape
            with ui.button(icon='palette') \
                    .props('round unelevated size=sm aria-label="Fabric color"') \
                    .classes('shadow-lg') \
                    .tooltip('Fabric color') as self.ui_fabric_color_btn:
                self.ui_fabric_color_picker = ui.color_picker(
                    on_pick=lambda e: self.update_fabric_color(e.color))
            self.ui_fabric_color_picker.set_color(self.pattern_state.fabric_color)
            self.ui_fabric_color_btn.style(
                f'background-color: {self.pattern_state.fabric_color} !important')

        # Floating attribution
        with ui.row(wrap=False).classes(
                'absolute bottom-2 left-3 z-40 se-overlay-chip items-center '
                'gap-1 px-2.5 py-0.5 text-[0.7rem]'):
            ui.link('© 2024 Interactive Geometry Lab', 'https://igl.ethz.ch/',
                    new_tab=True).classes('text-[#5a6270]')
            ui.label('·').classes('text-[#5a6270] opacity-60')
            ui.link('Built on GarmentCode',
                    'https://github.com/maria-korosteleva/GarmentCode',
                    new_tab=True).classes('text-[#5a6270]')

    # !SECTION
    # SECTION -- Configuration side panel
    def def_side_panel(self):
        """Collapsible configuration panel: body source + design parameters"""
        # NOTE: kept for compatibility with the shared update flow —
        # measurement editing lives on the account page now
        self.ui_active_body_refs = {}
        self.ui_passive_body_refs = {}

        ui.button(icon='chevron_left', on_click=self.ui_side_panel.toggle) \
            .props('flat dense round size=sm color=grey-7 aria-label="Collapse panel"') \
            .classes('absolute top-1.5 right-1.5 z-10').tooltip('Collapse panel')

        ui.label('Body').classes('se-section-label')
        account_widgets.body_source_ui(self)

        ui.separator().classes('my-2')

        ui.label('Garment').classes('se-section-label')
        self.def_design_block()

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
                p_range = design_params[param]['range']
                if 'select' in p_type:
                    values = design_params[param]['range']
                    if 'null' in p_type and None not in values: 
                        values.append(None)  # NOTE: Displayable value
                    ui.label(param_name).classes('p-0 m-0 mt-2 se-param-label')
                    ui_elems[param] = ui.select(
                        values, value=val,
                        on_change=lambda e, dic=design_params, param=param: self.update_pattern_ui_state(dic, param, e.value)
                    ).classes('w-full').props('outlined dense options-dense')
                elif p_type == 'bool':
                    ui_elems[param] = ui.switch(
                        param_name, value=val, 
                        on_change=lambda e, dic=design_params, param=param: self.update_pattern_ui_state(dic, param, e.value)
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
                            lambda e, dic=design_params, param=param: self.update_pattern_ui_state(dic, param, e.args))

                    # NOTE 'change' fires when the user releases the slider:
                    # one draft per adjustment instead of one per drag tick
                    # (the 'label' prop still shows the live value while dragging)
                elif 'file' in p_type:
                    print(f'GUI::NotImplementedERROR::{param}::'
                          '"file" parameter type is not yet supported in Web SewEasy. '
                          'Creation of corresponding UI element skipped'
                    )
                else:
                    print(f'GUI::WARNING::Unknown parameter type: {p_type}')
                    ui_elems[param] = ui.input(label=param_name, value=val, placeholder='Type the value',
                        validation={'Input too long': lambda value: len(value) < 20},
                        on_change=lambda e, dic=design_params, param=param: self.update_pattern_ui_state(dic, param, e.value)
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
                on_change=lambda e, dic=meta, param=param: self.update_pattern_ui_state(dic, param, e.value)
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
            if self.user:
                account_widgets.designs_ui(self)

        # Parameter sections -- only those the current composition reads
        # are visible (see _refresh_section_relevance)
        with ui.column().classes('w-full gap-2 mt-3'):
            for section in design_params:
                if section == 'meta':
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

        relevant = set()
        if upper == 'DressShirt':
            # Self-contained: own section + sleeves + buttons (no generic
            # collar/asym)
            relevant |= {'dress_shirt', 'sleeve', 'buttons'}
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
        """Prepare pattern display area: a pannable drafting workspace
        with floating controls"""
        with ui.column().classes('w-full h-full p-0 m-0 gap-0'):
            with ui.element('div').classes('se-workspace w-full h-full'), ui.image(
                    f'{self.path_static_img}/millimiter_paper_1500_900.png'
                ).classes('w-[1400px] min-w-[1400px] h-[840px] min-h-[840px] m-auto p-0')  as self.ui_pattern_bg:
                # NOTE: Positioning: https://github.com/zauberzeug/nicegui/discussions/957 
                with ui.row().classes('w-full h-full p-0 m-0 bg-transparent relative top-[0%] left-[0%]'):
                    self.body_outline_classes = 'bg-transparent h-full absolute top-[0%] left-[0%] p-0 m-0'
                    self.ui_body_outline = ui.image(f'{self.path_static_img}/ggg_outline_mean_all.svg') \
                        .props('alt="Body silhouette behind the pattern"') \
                        .classes(self.body_outline_classes)
                
                # NOTE: ui.row allows for correct classes application (e.g. no padding on svg pattern)
                with ui.row().classes('w-full h-full p-0 m-0 bg-transparent relative'):
                    # Automatically updates from source
                    self.ui_pattern_display = ui.interactive_image(
                        ''
                    ).classes('bg-transparent p-0 m-0')

            # Floating controls over the workspace
            # NOTE: stacked vertically so they never collide with the
            # centered view switcher on narrow windows
            with ui.column().classes('absolute top-3 left-4 z-40 items-start gap-2'):
                ui.switch(
                    'Body Silhouette', value=True,
                ).props('dense left-label').classes('se-overlay-chip text-stone-800 pl-2.5 pr-1.5 py-0.5') \
                    .bind_value(self.ui_body_outline, 'visible')
                self.ui_self_intersect = ui.label(
                    'Garment panels are self-intersecting'
                ).classes('se-warning-chip') \
                    .bind_visibility(self.pattern_state, 'is_self_intersecting')

            # Floating primary action
            ui.button('Download pattern', on_click=lambda: self.state_download()) \
                .props('unelevated icon=download') \
                .classes('absolute bottom-5 right-6 z-50 shadow-lg')

    # !SECTION
    # SECTION 3D view
    def create_lights(self, scene:ui.scene, intensity=30.0):
        light_positions = np.array([
            [1.60614, 1.23701, 1.5341,],
            [1.31844, -2.52238, 1.92831],
            [-2.80522, 2.34624, 1.2594],
            [0.160261, 3.52215, 1.81789],
            [-2.65752, -1.26328, 1.41194]
        ])
        light_colors = [
            '#ffffff',
            '#ffffff',
            '#ffffff',
            '#ffffff',
            '#ffffff'
        ]
        z_dirs = np.arctan2(light_positions[:, 1], light_positions[:, 0])

        # Add lights to the scene
        for i in range(len(light_positions)):
            scene.spot_light(
                color=light_colors[i], intensity=intensity,
                angle=np.pi,
                ).rotate(0., 0., -z_dirs[i]).move(light_positions[i][0], light_positions[i][1], light_positions[i][2])

    def create_camera(self, cam_location, fov, scale=1.):
        camera = ui.scene.perspective_camera(fov=fov)
        camera.x = cam_location[0] * scale
        camera.y = cam_location[1] * scale
        camera.z = cam_location[2] * scale

        # direction
        camera.look_at_x = 0
        camera.look_at_y = 0
        camera.look_at_z = cam_location[2] * scale * 2/3

        return camera

    def def_3d_scene(self):
        y_fov = 30   # Degrees == np.pi / 6. rad FOV
        camera_location = [0, -4.15, 1.25]
        bg_color = '#f7f5f0'  # pattern paper

        def body_visibility(value):
            self.ui_body_3d.visible(value)

        camera = self.create_camera(camera_location, y_fov)
        with ui.scene(
            width=self.scene_base_resoltion[0],
            height=self.scene_base_resoltion[1],
            camera=camera,
            grid=False,
            background_color=bg_color
            ).classes('w-full h-full p-0 m-0') as self.ui_3d_scene:
            # Lights setup
            self.create_lights(self.ui_3d_scene, intensity=10.)
            # NOTE: texture is there, just needs a better setup
            self.ui_garment_3d = None
            # TODOLOW Update body model to a correct shape
            # NOTE: decimated GLB (9k faces, ~180KB vs the 2.3MB full STL)
            # with the muslin color baked in — loads much faster
            self.ui_body_3d = self.ui_3d_scene.gltf(
                    '/body/mean_all_display.glb'
                ).rotate(np.pi / 2, 0., 0.)

        # Floating controls over the 3D stage
        # NOTE: stacked vertically so they never collide with the
        # centered view switcher on narrow windows
        with ui.column().classes('absolute top-3 left-4 z-40 items-start gap-2'):
            self.ui_body_3d_switch = ui.switch(
                'Body Silhouette',
                value=True,
                on_change=lambda e: body_visibility(e.value)
            ).props('dense left-label').classes('se-overlay-chip text-stone-800 pl-2.5 pr-1.5 py-0.5')

            # Mannequin skin tone
            with ui.element('div').classes('se-overlay-chip w-44 px-4 pt-0.5'):
                self.ui_skin_slider = ui.slider(
                    value=skin_tone_t(self.body_color)
                        if self.body_color != DEFAULT_BODY_COLOR else 0.3,
                    min=0., max=1., step=0.01,
                ).props('dense aria-label="Mannequin skin tone"') \
                    .classes('se-skin-slider w-full') \
                    .style(f'color: {self.body_color}') \
                    .on('change',
                        lambda e: self.update_body_color(skin_tone_hex(e.args))) \
                    .tooltip('Mannequin skin tone')

            # The 3D result goes stale as soon as the design changes;
            # make the required re-drape step visible instead of implied
            self.ui_3d_stale = ui.label(
                'Press "Drape current design" to see this design in 3D'
            ).classes('se-warning-chip') \
                .bind_visibility_from(self.pattern_state, 'is_in_3D',
                                      backward=lambda in_3d: not in_3d)

        # Floating primary action
        ui.button('Drape current design', on_click=lambda: self.update_3d_scene()) \
            .props('unelevated icon=checkroom').classes('absolute bottom-5 right-6 z-50 shadow-lg') \
            .tooltip('The first drape can take a couple of minutes')

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
    async def update_pattern_ui_state(self, param_dict=None, param=None, new_value=None, body_param=False):
        """UI was updated -- update the state of the pattern parameters and visuals"""
        # NOTE: Fixing to the "same value" issue in lambdas 
        # https://github.com/zauberzeug/nicegui/wiki/FAQs#why-have-all-my-elements-the-same-value
   
        print('INFO::Updating pattern...')

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
        finally:
            self.spin_dialog.close()  # If open

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
        """Sync the pattern canvas with the current pattern state"""
        # TODOLOW the pattern is floating around when collars are added..
        if self.ui_pattern_display is not None:

            if self.pattern_state.svg_filename:
                # Re-align the canvas and body with the new pattern
                p_bbox_size = self.pattern_state.svg_bbox_size
                p_bbox = self.pattern_state.svg_bbox

                # Margin calculations w.r.t. canvas size
                # s.t. the pattern scales correctly
                w_shift = abs(p_bbox[0])  # Body feet location in width direction w.r.t top-left corner of the pattern
                m_top = (1. - abs(p_bbox[2]) * self.background_body_scale) * self.h_rel_body_size + (1. - self.h_rel_body_size) / 2 
                m_left = self.background_body_canvas_center - w_shift * self.background_body_scale * self.w_rel_body_size
                m_right = 1 - m_left - p_bbox_size[0] * self.background_body_scale * self.w_rel_body_size
                m_bottom = 1 - m_top - p_bbox_size[1] * self.background_body_scale * self.h_rel_body_size

                # Canvas padding adjustment
                m_top -= self.h_canvas_pad
                m_left -= self.w_canvas_pad
                m_right += self.w_canvas_pad  # preserve evaluated width
                m_bottom -= self.h_canvas_pad

                # New placement
                if m_top < 0 or m_bottom < 0 or m_left < 0 or m_right < 0:
                    # Calculate the fraction
                    scale_margin = 1.2
                    y_top_scale = abs(min(m_top * scale_margin, 0.)) + 1.
                    y_bot_scale = 1. + abs(min(m_bottom * scale_margin, 0.))
                    x_left_scale = abs(min(m_left * scale_margin, 0.)) + 1.
                    x_right_scale = abs(min(m_right * scale_margin, 0.)) + 1.
                    scale = min(1. / y_top_scale, 1. / y_bot_scale, 1. / x_left_scale, 1. / x_right_scale)

                    # Rescale the body
                    self.ui_body_outline.classes(
                        replace=self.body_outline_classes + f' origin-center scale-[{scale}]'
                    )

                    # Recalculate positioning & width
                    body_center = 0.5 - self.background_body_canvas_center
                    m_top = (1. - abs(p_bbox[2]) * self.background_body_scale) * self.h_rel_body_size * scale + (1. - self.h_rel_body_size * scale) / 2 
                    m_left = (0.5 - body_center * scale) - w_shift * self.background_body_scale * self.w_rel_body_size * scale
                    m_right = 1 - m_left - p_bbox_size[0] * self.background_body_scale * self.w_rel_body_size * scale

                    # Canvas padding adjustment
                    # TODOLOW For some reason top adjustment is not needed here: m_top -= self.h_canvas_pad * scale
                    m_left -= self.w_canvas_pad * scale
                    m_right += self.w_canvas_pad * scale

                else:  # Display normally 
                    # Remove body transforms if any were applied
                    self.ui_body_outline.classes(replace=self.body_outline_classes)

                # New pattern image
                self.ui_pattern_display.set_source(
                    str(self.pattern_state.svg_path()) if self.pattern_state.svg_filename else '')
                self.ui_pattern_display.classes(
                        replace=f"""bg-transparent p-0 m-0
                                absolute 
                                left-[{m_left * 100}%]
                                top-[{m_top * 100}%] 
                                w-[{(1. - m_right - m_left) * 100}%]
                                height-auto
                        """)  
                    
            else:
                # Restore default state
                self.ui_pattern_display.set_source('')
                self.ui_body_outline.classes(replace=self.body_outline_classes)

    def update_design_params_ui_state(self, ui_elems, design_params):
        """Sync ui params with the current state of the design params"""
        for param in design_params: 
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

    async def update_3d_scene(self):
        """According the whatever pattern current state"""

        print('INFO::Updating 3D...')

        # Cleanup 
        if self.ui_garment_3d is not None:
            self.ui_garment_3d.delete()
            self.ui_garment_3d = None
        
        if not self.pattern_state.svg_filename:
            print('INFO::Current garment is empty, skipped 3D update')
            ui.notify('Current garment is empty. Chose a design to start simulating!')
            self.ui_body_3d.visible(True)
            self.ui_body_3d_switch.set_value(True)
            return

        try:
            # Display waiting spinner untill getting the result
            # NOTE Splashscreen solution to block users from modifying params while updating
            # https://github.com/zauberzeug/nicegui/discussions/1988

            self.open_spinner('Simulating the 3D drape — this can take '
                              'a couple of minutes on the first run')
            # NOTE: Using threads for async call
            # https://stackoverflow.com/questions/49822552/python-asyncio-typeerror-object-dict-cant-be-used-in-await-expression
            self.loop = asyncio.get_event_loop()
            await self.loop.run_in_executor(self._async_executor, self._sync_update_3d)

            # Update ui
            # https://github.com/zauberzeug/nicegui/discussions/1269
            with self.ui_3d_scene:
                # NOTE: material is defined in the glb file
                self.ui_garment_3d = self.ui_3d_scene.gltf(
                            f'geo/{self.garm_3d_filename}',
                        ).scale(0.01).rotate(np.pi / 2, 0., 0.)

        except Exception as e:
            traceback.print_exc()
            print(e)
            self.ui_3d_scene.set_visibility(True)
            ui.notify(
                'The drape simulation failed — this is usually on our side, '
                'not your design. Try again, or adjust the parameters if it persists',
                type='negative',
                close_button=True,
                position='center'
            )
        finally:
            self.spin_dialog.close()  # If open
    
    def _sync_update_3d(self):
        """Update 3d model"""

        # Run simulation
        path, filename = self.pattern_state.drape_3d()

        # NOTE: The files will be available publically at the static point
        # However, we cannot do much about it, since it won't be available for the interface otherwise
        
        # Delete previous file
        (self.local_path_3d / self.garm_3d_filename).unlink(missing_ok=True)
        # Put the new one for display
        self.garm_3d_filename = f'garm_3d_{self.pattern_state.id}_{time.time()}.glb'
        shutil.copy2(path / filename, self.local_path_3d / self.garm_3d_filename)

    async def update_fabric_color(self, color):
        """Apply a new fabric color to the 2D pattern and the draped 3D garment"""
        if not color or color == self.pattern_state.fabric_color:
            return

        print('INFO::Updating fabric color...')
        self.ui_fabric_color_btn.style(f'background-color: {color} !important')

        self.loop = asyncio.get_event_loop()

        # 2D: SVG re-serialization of the already-assembled pattern —
        # still an assembly+render pass, so keep it off the event loop
        await self.loop.run_in_executor(
            self._async_executor, self.pattern_state.set_fabric_color, color)
        self.update_pattern_display()

        # 3D: re-tint the existing drape -- material re-export only,
        # no re-simulation needed (covers fresh sims and adopted drapes)
        if self.ui_garment_3d is None:
            return
        try:
            self.open_spinner('Applying the fabric color to the 3D drape…')
            updated = await self.loop.run_in_executor(
                self._async_executor, self._sync_recolor_3d)

            if updated:
                self.ui_garment_3d.delete()
                with self.ui_3d_scene:
                    self.ui_garment_3d = self.ui_3d_scene.gltf(
                                f'geo/{self.garm_3d_filename}',
                            ).scale(0.01).rotate(np.pi / 2, 0., 0.)
        except Exception as e:
            traceback.print_exc()
            print(e)
            ui.notify(
                'Failed to apply the fabric color to the 3D view',
                type='negative',
                close_button=True,
                position='center'
            )
        finally:
            self.spin_dialog.close()  # If open

    async def update_body_color(self, color):
        """Re-tint the 3D mannequin with the chosen skin tone"""
        if not color or color == self.body_color:
            return

        print('INFO::Updating mannequin color...')
        self.body_color = color
        self.ui_skin_slider.style(f'color: {color}')   # thumb shows the tone

        try:
            # Tinted exports are cached by tone and shared across sessions
            # (see webapp.body_display); only a cache miss does mesh work
            self.loop = asyncio.get_event_loop()
            url = await self.loop.run_in_executor(
                self._async_executor, body_display.tinted_body_glb_url, color)

            # Swap the body model in the scene, preserving visibility
            visible = self.ui_body_3d_switch.value
            self.ui_body_3d.delete()
            with self.ui_3d_scene:
                self.ui_body_3d = self.ui_3d_scene.gltf(url) \
                    .rotate(np.pi / 2, 0., 0.)
            self.ui_body_3d.visible(visible)
        except Exception as e:
            traceback.print_exc()
            print(e)
            ui.notify(
                'Failed to apply the mannequin color',
                type='negative',
                close_button=True,
                position='center'
            )

    async def apply_skin_color(self, color):
        """Apply a stored skin tone (None -> default muslin) and sync the
        slider position + thumb color to it"""
        color = color or DEFAULT_BODY_COLOR
        self.ui_skin_slider.set_value(skin_tone_t(color))
        self.ui_skin_slider.style(f'color: {color}')
        await self.update_body_color(color)

    def _sync_recolor_3d(self):
        """Re-export the draped garment GLB in the current fabric color"""
        res = self.pattern_state.recolor_3d()
        if res is None:
            return False
        path, filename = res

        # Delete previous file
        (self.local_path_3d / self.garm_3d_filename).unlink(missing_ok=True)
        # Put the new one for display
        self.garm_3d_filename = f'garm_3d_{self.pattern_state.id}_{time.time()}.glb'
        shutil.copy2(path / filename, self.local_path_3d / self.garm_3d_filename)
        return True

    def apply_fabric_color_visuals(self, color):
        """Set the fabric color state + 2D display (no 3D export) —
        used when a saved outfit restores its color"""
        if not color or color == self.pattern_state.fabric_color:
            return
        self.pattern_state.fabric_color = color
        self.ui_fabric_color_btn.style(f'background-color: {color} !important')
        self.ui_fabric_color_picker.set_color(color)

    def adopt_drape(self, glb_bytes):
        """Show a stored drape in the 3D scene without re-simulating"""
        self.pattern_state.adopt_drape_glb(glb_bytes)

        # Delete previous file
        (self.local_path_3d / self.garm_3d_filename).unlink(missing_ok=True)
        # Put the new one for display
        self.garm_3d_filename = f'garm_3d_{self.pattern_state.id}_{time.time()}.glb'
        (self.local_path_3d / self.garm_3d_filename).write_bytes(glb_bytes)

        if self.ui_garment_3d is not None:
            self.ui_garment_3d.delete()
        with self.ui_3d_scene:
            self.ui_garment_3d = self.ui_3d_scene.gltf(
                        f'geo/{self.garm_3d_filename}',
                    ).scale(0.01).rotate(np.pi / 2, 0., 0.)

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
