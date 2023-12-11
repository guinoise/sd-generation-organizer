from typing import Optional
from generation_organizer.helpers import logger as helper_logger, base_dir, temp_dir
from modules import script_callbacks, shared, scripts
from modules.ui import create_refresh_button, ToolButton
import gradio as gr
import pychromecast
from generation_organizer.casting import CastConfiguration, CastType, ImageInfo, ImageType, CastThread
from datetime import datetime
from matplotlib import font_manager
import socket
from queue import Empty, Full, Queue
from modules.processing import StableDiffusionProcessing, Processed
from threading import Event

logger= helper_logger.getChild(__name__)
#symbol_stop= '⏹️'
symbol_stop= '🛑'
symbol_play= '▶️'
## EMOJI https://emojipedia.org/
## Variables
logger.info("Importing module, defining variable")
initial_scan_done: bool= False
selected_font= None
selected_font= None
casting: bool= False
cast_devices= []
image_queue: Optional[Queue[ImageInfo]]= None
cast_thread: Optional[CastThread]= None
cast_thread_stop_event: Event= Event()
base_url: str= None
btn_casting: ToolButton= None
# End Variables

class CastingScript(scripts.Script):

    def __init__(self):
        super().__init__()
        logger.debug("CastingScript::__init__")
        self._send_to_cast_thread= False
        #script_callbacks.on_app_started(lambda block, _: self.on_app_started(block))

    def title(self):
        logger.debug("CastingScript::title")
        """this function should return the title of the script. This is what will be displayed in the dropdown menu."""
        return "Casting"
    
    def show(self, is_img2img):
        """
        is_img2img is True if this function is called for the img2img interface, and Fasle otherwise

        This function should return:
         - False if the script should not be shown in UI at all
         - True if the script should be shown in UI if it's selected in the scripts dropdown
         - script.AlwaysVisible if the script should be shown in UI at all times
         """
        logger.debug("CastingScript::show")
        logger.debug("Args %20s (%s) %r", "is_img2img", type(is_img2img), is_img2img)
        return scripts.AlwaysVisible

    def postprocess_image(self, p: StableDiffusionProcessing, pp: scripts.PostprocessImageArgs, *args):
        """
        Called for every image after it has been generated.
        """
        logger.debug("CastingScript::postprocess_image")
        if not casting:
            return
        logger.debug("Args %20s (%s) %r", "p", type(p), p)
        logger.debug("Args %20s (%s) %r", "pp", type(pp), pp)
        logger.debug("Args %20s %r", "args", args)
        if issubclass(type(pp), Processed):
            logger.info("postprocess_image: Processed")
            info= ImageInfo(ImageType.STABLE_DIFFUSION_PROCESSED, obj= pp, creation_date=datetime.now(), message= None)
            self._enqueue(info)
        if issubclass(type(pp), scripts.PostprocessImageArgs):
            logger.info("postprocess_image: PostprocessImageArgs")
            logger.info("p :(%s) %s", type(p), p)
            messages=[]
            messages.append(f"PostprocessImageArgs {p.n_iter}/{p.batch_size}")
            messages.append(f"seed {p.seeds[p.iteration]}")
            #messages.append(f"eta {p.eta}")
            info= ImageInfo(ImageType.PIL, obj= pp.image, creation_date=datetime.now(), message= messages)
            self._enqueue(info)
        elif issubclass(type(p), StableDiffusionProcessing):
            logger.info("postprocess_image: StableDiffusionProcessing")
            info= ImageInfo(ImageType.STABLE_DIFFUSION_PROCESSING, obj= pp, creation_date=datetime.now(), message= None)            
            self._enqueue(info)
        else:
            logger.warning("PP: Unsuported type %s", type(pp))

    def _enqueue(self, img_info: ImageInfo):
        if image_queue is None:
            logger.error("Queue object not found, discarding object")
            return
        if image_queue.full():
            logger.warning("Queue was full, dropping one object")
            try:
                image_queue.get_nowait()
            except Empty:
                pass
        try:
            image_queue.put_nowait(img_info)
        except Full:
            logger.warning("Error queueing image, queue full")            



def on_ui_settings():
    logger.debug("on_ui_settings")

    section = ("sd_webui_generation_organizer", "Generation organizer")
    # shared.opts.add_option(
    #     "cast_output",
    #     shared.OptionInfo(
    #         False,
    #         "Cast",
    #         gr.Checkbox,
    #         {"interactive": True},
    #         section=section,
            
    #     ),
    # )
    infotext= """
Casting to chromecast require a webserver in http diffusing locally on the network.
This setting is to set the port used for this webserver.
Default is 7861, one port over the default stable diffusion webui port.
Limited to unprivileged port between 1024 and 32000
"""
    shared.opts.add_option(
        "casting_support_web_server_port",
        shared.OptionInfo(
            7861,
            "Port for the webserver for casting (chromecast required)",
            gr.Number,
            {"minimum": 1024, "maximum": 32000, "step": 1, "interactive": True, "info": infotext, "visible": False},
            section=section,
        ).needs_restart(),
    )
    infotext= """
When the server start (restart, reload, reload ui), try to reconnect to last active casting device.
"""    
    shared.opts.add_option(
        "casting_autoreconnect_onstart",
        shared.OptionInfo(
            False,
            "Resume casting on start",
            gr.Checkbox,
            {"interactive": True, "visible": True},
            section=section,
        ),
    )  

     
def get_cast_devices_list():
    logger.debug("get_cast_devices_list : %s", cast_devices)
    return cast_devices

def refresh_cast_devices():
    logger.info("Scan from casting devices, chromecast")
    chromecast_devices= []
    browser: pychromecast.CastBrowser
    services, browser = pychromecast.discovery.discover_chromecasts()
    #logger.debug("Services: ", services)
    browser.stop_discovery()
    device: pychromecast.models.CastInfo
    for device_uuid, device in browser.devices.items():
        logger.debug("Chrome discovery. UUID : %40s Name : %s", device_uuid, device.friendly_name)
        chromecast_devices.append(device.friendly_name)
    cast_devices.clear()
    cast_devices.extend(chromecast_devices) 
    #return gr.Dropdown.update(choices=get_cast_devices_list())

def start_casting(device_name: str) -> bool :
    global cast_thread, cast_thread_stop_event, image_queue
    logger.info("start_casting")
    if cast_thread is not None:
        logger.warning("Ask to start casting but already casting, stop first")
        stop_casting()

    if device_name not in cast_devices:
        logger.warning("Requested to start casting on %s but not in cast devices discoverd", device_name)
        return False
    logger.warning("start_casting")
    config= CastConfiguration(cast_type=CastType.CHROMECAST, device_name=device_name, base_callback_url=base_url, temp_dir=temp_dir, font_path=selected_font)
    #Just to be sure
    cast_thread_stop_event.clear()
    if image_queue is None:
        image_queue= Queue(maxsize=10)        
    cast_thread= CastThread(stop_event=cast_thread_stop_event, image_queue=image_queue, config=config)
    cast_thread.start()
    return True

def stop_casting():
    global cast_thread, cast_thread_stop_event
    logger.warning("stop_casting")
    if cast_thread is None:
        return
    
    logger.info("Request stop of cast thread")
    cast_thread_stop_event.set()
    logger.info("Wait for cast thread to teard down, max 5 seconds")
    cast_thread.join(timeout=5)
    cast_thread= None


def btn_casting_pushed(device, *args, **kwargs):
    global casting
    logger.debug("btn_casting_pushed")
    logger.debug("Args %20s (%s), %r", "device", type(device), device)
    logger.debug("Args %20s %r", "args", args)
    logger.debug("Args %20s %r", "kwargs", kwargs)
    logger.debug("btn_casting_pushed was casting: %s", casting)
    if casting:
        stop_casting()
        casting= False
    else:
        casting= start_casting(device_name=device)
    symbol= symbol_stop if casting else symbol_play
    return gr.Button.update(value=symbol)

def cast_setting_change(device_name, *args, **kwargs):
    global image_queue, cast_thread, cast_thread_stop_event, cast_devices, casting
    logger.debug("cast_setting_change")
    logger.debug("Args %20s %r", "args", args)
    logger.debug("Args %20s %r", "kwargs", kwargs)
    logger.debug("Device name : %s, is casting %s", device_name, casting)
    if casting:
        stop_casting()
        casting= start_casting(device_name=device_name)

    logger.debug("cast_setting_change casting value: %s", casting)
    symbol= symbol_stop if casting else symbol_play
    return gr.Button.update(value=symbol)
        
        
    # device_name= getattr(shared.opts, "cast_device", None)
    # casting= (getattr(shared.opts, "casting", False) 
    #           and device_name is not None
    #           and device_name in cast_devices)
    #logger.debug("Cast setting change. Casting option %5s Casting %5s device_name : %s devices: %s", getattr(shared.opts, "casting", None), casting, device_name, cast_devices)
    # if casting and device_name and cast_thread is None:
    #     logger.warning("Starting casting thread")
    #     config= CastConfiguration(cast_type=CastType.CHROMECAST, 
    #                               device_name=device_name, 
    #                               base_callback_url=base_url, 
    #                               temp_dir=temp_dir,
    #                               font_path=selected_font)
    #     #Just to be sure
    #     cast_thread_stop_event.clear()
    #     if image_queue is None:
    #         image_queue= Queue(maxsize=10)        
    #     cast_thread= CastThread(stop_event=cast_thread_stop_event, image_queue=image_queue, config=config)
    #     cast_thread.start()
    # elif cast_thread is not None:
    #     logger.warning("Shutdown casting thread")
    #     logger.info("Request stop of cast thread")
    #     cast_thread_stop_event.set()
    #     logger.info("Wait for cast thread to teard down, max 5 seconds")
    #     cast_thread.join(timeout=5)
    #     cast_thread= None
    # if getattr(shared.opts, "casting", False) and cast_thread is None:
    #     shared.opts.set("casting", False, run_callbacks=False)       
    #     gr.Error(f"Device {device_name} is not discovered")
            
    
def on_ui_tab(**_kwargs):
    global btn_casting
    """register a function to be called when the UI is creating new tabs.
    The function must either return a None, which means no new tabs to be added, or a list, where
    each element is a tuple:
        (gradio_component, title, elem_id)

    gradio_component is a gradio component to be used for contents of the tab (usually gr.Blocks)
    title is tab text displayed to user in the UI
    elem_id is HTML id for the tab
    """    
    with gr.Blocks(analytics_enabled=False) as tab:
        with gr.Row(elem_id="generation_organizer_casting_row"):
            dd_devices= gr.Dropdown(get_cast_devices_list(), 
                           value=None,
                           label="Casting device",
                           interactive=True,
                           elem_id="generation_organizer_casting_devices")
            #btn_rescan= gr.Button("🔄", visible=True)
            #btn_rescan.click(fn=refresh_cast_devices, outputs=[dd_devices])
            # create_refresh_button(
            #     self.checkpoint_dropdown,
            #     refresh_checkpoints,
            #     lambda: {"choices": get_checkpoint_choices()},
            #     f"refresh_{id_part}_checkpoint",
            # )
            create_refresh_button(dd_devices, refresh_cast_devices, lambda: {"choices": get_cast_devices_list()}, "generation_organizer_casting_devices_refresh")
            btn_casting= ToolButton(value=symbol_stop if casting else symbol_play, 
                                    elem_id="generation_organizer_casting",
                                    tooltip="Cast")

            dd_devices.change(fn=cast_setting_change, inputs=dd_devices, outputs=btn_casting)
            btn_casting.click(
                fn=btn_casting_pushed,
                inputs=dd_devices,
                outputs=btn_casting
            )
            # refresh_button = ToolButton(value=refresh_symbol, elem_id=elem_id, tooltip=f"{label}: refresh" if label else "Refresh")
            # refresh_button.click(
            #     fn=refresh,
            #     inputs=[],
            #     outputs=refresh_components
            # )            
            #im_cast= gr.Image(type="filepath", value=base_dir.joinpath('assets/cast-logo.png'), visible=True, interactive=False, width=32)
            
            
    return [(tab, "Generation organizer", "generation_organizer_tab")]

def on_before_ui():
    global initial_scan_done
    logger.info("Before UI (module)")
    # if casting and cast_thread is None:
    #     logger.debug("Casting was enabled but just restarting, disable it")
    #     shared.opts.set("casting", False, run_callbacks=False) 
    if not initial_scan_done:
        logger.info("Initial scanning of devices")               
        refresh_cast_devices()
        initial_scan_done= True

def on_app_started(block: gr.Blocks, app):
    global initial_scan_done, selected_font, base_url
    logger.info("App started (module)")
    logger.info("Data path: %s", shared.data_path)
#    casting= getattr(shared.opts, "casting", False)
    prefered_font=["FreeMono", "Ubuntu Mono"]
    all_fonts= font_manager.get_font_names()
    selected_font= None
    for f in prefered_font:
        if f in all_fonts:
            selected_font= f
            break
    else:
        for f in all_fonts:
            if "Mono" in f:
                selected_font= f
                break
        else:
            selected_font= all_fonts[0]
    selected_font= font_manager.findfont(selected_font)
    if not temp_dir.is_dir():
        logger.warning("Creating temp dir %s", temp_dir.resolve())
        temp_dir.mkdir(parents=True)
    gradio_allowed_path= getattr(shared.opts, "gradio_allowed_path", [])
    if temp_dir.resolve() not in gradio_allowed_path:   
        #TODO removed when local webserver is added     
        logger.info("Add temp dir to gradio allowed path")
        shared.cmd_opts.gradio_allowed_path.append(temp_dir.resolve()) 

    port= getattr(shared.opts, "port", 7860)
    default_listen_ip= None
    try:     
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        default_listen_ip= s.getsockname()[0]
        s.close()
    except Exception as e:
        logger.exception("Error on finding local IP")

    logger.debug("Default listen IP : %s", default_listen_ip)
    base_url= "http://{}:{}/file=".format(default_listen_ip, port)




script_callbacks.on_ui_settings(on_ui_settings)
script_callbacks.on_ui_tabs(on_ui_tab)
script_callbacks.on_before_ui(on_before_ui)
script_callbacks.on_app_started(on_app_started)

