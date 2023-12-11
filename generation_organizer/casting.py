from generation_organizer.helpers import logger as helper_logger, base_dir, temp_dir
from dataclasses import dataclass
from enum import Enum
import pathlib
from typing import Union, List, Tuple, Optional
from datetime import datetime
import torchvision.transforms as transforms
from math import ceil, sqrt
from PIL import Image, ImageDraw, ImageFont, ImageOps
from PIL.Image import Image as ImagePIL
from PIL.ImageDraw import ImageDraw as ImageDrawPIL
from torch import Tensor
from textwrap import TextWrapper
from modules.processing import StableDiffusionProcessing, Processed
import tempfile
from PIL.ImageFont import FreeTypeFont
import itertools
from threading import Thread, Event
import pychromecast
from queue import Queue, Empty, Full
import gradio as gr
import time
from modules import shared
from modules.shared_state import State

logger= helper_logger.getChild(__name__)

class TvAspects(Enum):
    ASPECT_4_3= (4,3)
    ASPECT_16_9= (16,9)

class ImageType(Enum):
    FILE= "File"
    TENSOR= "torch Tensor"
    PIL= "Pillow Image"
    STABLE_DIFFUSION_PROCESSED= "Stable diffusion processed"
    STABLE_DIFFUSION_PROCESSING= "Stable diffusion processing"
    
class CastType(Enum):
    CHROMECAST= "ChromeCast"
    AIRPLAY= "AirPlay"

@dataclass
class CastConfiguration:
    cast_type: CastType
    device_name: str
    base_callback_url: str
    temp_dir: pathlib.Path
    font_path: Optional[str]

@dataclass
class ImageInfo:
    image_type: ImageType
    obj: any
    creation_date: datetime
    message: Union[str, List[str], None]
    

def aspect_resize(w: int, h: int, aspect: TvAspects) -> Tuple[int,int]:
    target_ratio= aspect.value[0] / aspect.value[1]
    current_ratio= w / h
    if current_ratio < target_ratio:
        new_w = w * (target_ratio/current_ratio)
        new_h = h
    else:
        new_w = w 
        new_h = h * (target_ratio/current_ratio)
    logger.debug("Aspect resize : ratio %d/%d %7.5f w: %5d %5d h: %5d %5d final ratio %7.5f", aspect.value[0], aspect.value[1],target_ratio, w, h, new_w, new_h, new_w/new_h)
    return (new_w, new_h)

class CastingImageInfo():
    image_info: ImageInfo
    image_path: pathlib.Path
    mime_type: str
    config: CastConfiguration
    url: str
    _ready: bool
    _torch_to_pil: transforms.ToPILImage= transforms.ToPILImage()
    _path: pathlib.Path

    def _get_grid_size(number_of_items: int) -> Tuple[int,int]:
        columns = int(sqrt(number_of_items))
        lines = int(ceil(number_of_items / columns))
        return (columns, lines)

  
    def __init__(self, image_info: ImageInfo, config: CastConfiguration):
        self.image_info= image_info
        self.config= config
        self._ready= False
        self.aspect= TvAspects.ASPECT_16_9
        try:
            im: ImagePIL= None
            if self.image_info.image_type == ImageType.TENSOR:
                prefix='torch_to_pil_'
                obj: Tensor= self.image_info.obj
                im= self._tensor_to_pil(obj)
            elif self.image_info.image_type == ImageType.FILE:
                prefix='from_file_'
                im: ImagePIL= Image.open(self.image_info.obj)
            elif self.image_info.image_type == ImageType.PIL:
                prefix='from_pil_'
                im: ImagePIL= self.image_info.obj
            elif self.image_info.image_type == ImageType.STABLE_DIFFUSION_PROCESSED:
                prefix='sd_processed_'
                obj: Processed= self.image_info.obj
                im: ImagePIL= self._join_images(obj.images)
            elif self.image_info.image_type == ImageType.STABLE_DIFFUSION_PROCESSING:
                prefix='sd_processing_'
                obj: StableDiffusionProcessing= self.image_info.obj
                im: ImagePIL= self._join_images()
            if image_info.message is None:
                text= []
            elif issubclass(type(image_info.message), str):
                text= [image_info.message]
            else:
                text= image_info.message
            
            text_padding= "_" * 22
            if im.info is not None:
                v: str
                for k,v in im.info.items():
                    lines= v.splitlines()
                    text.append(f"{k:20s} : {lines[0]}")
                    for i in range(1,len(lines)):
                        text.append(f"{text_padding} {lines[i]}")

            im= self.add_text_to_im(im, image_info.message, image_info.creation_date)
            self._file= tempfile.NamedTemporaryFile(suffix='.png', prefix=prefix, dir=self.config.temp_dir, delete=False)
            self._path= pathlib.Path(self._file.name)
            im.save(self._path)
            self.url= "{}{}".format(self.config.base_callback_url, self._file.name.replace('\\', '/'))
            self.mime_type= "image/png"
            self._ready= True

        except Exception as e:
            logger.exception("Error processing image : %s", str(e))

    def add_text_to_im(self, im: ImagePIL, text: Union[str, List[str], None], date: datetime) -> ImagePIL:
        td= datetime.now().replace(microsecond=0) - date.replace(microsecond=0)
        date_text= "{} ({})".format(date.strftime('%Y-%m-%d %H:%M:%S'), td)
        if text is None:
            text= date_text
        if issubclass(type(text), str):
            text= [date_text, text]
        else:
            text.insert(0, date_text)

        w,h= im.size
        logger.debug("SIZE %20s w %5d h %5d", "orig", w, h)

        wrapper: TextWrapper= TextWrapper()
        font_size= int(h*0.03)
        logger.info("Selected font: %s", self.config.font_path)
        try:
            font: FreeTypeFont= ImageFont.truetype(self.config.font_path, size=font_size)
            font_w= font.getlength("_")
        except Exception as e:
            logger.exception("Error loading TTF font, fallback to default : %s", str(e))
            font: ImageFont= ImageFont.load_default()
            # Approximation
            font_w= int(font_size * 0.4)
        logger.debug("SIZE %20s w %5d h %5d", "font", font_w, font_size)
        r_w, r_h= aspect_resize(w + font_size * (len(text) + 2 ), h, self.aspect)
        logger.debug("SIZE %20s w %5d h %5d", "aspect1", r_w, r_h)

        max_char= int(r_w / font_w)
        logger.debug("Font size : %5d max_char %d", font_size, max_char)

        wrapper.width= int(r_w / font_w)
        lines = [wrapper.wrap(i) for i in text]
        lines = list(itertools.chain.from_iterable(lines))

        r_h= int(h + ((len(lines)+1) * (font_size + 3)))
        r_w= int(self.aspect.value[0]/self.aspect.value[1]*r_h)
        lr_borders= int((r_w - w) / 2)
        b_border= r_h - h
        # Redo text wrapping after image resizing
        max_char= int(r_w / font_w)
        logger.debug("Font size : %5d max_char %d", font_size, max_char)

        wrapper.width= int(r_w / font_w)
        lines = [wrapper.wrap(i) for i in text]
        lines = list(itertools.chain.from_iterable(lines))

        logger.debug("SIZE %20s w %5d h %5d", "aspect2", r_w, r_h)
        logger.debug("Add text. w %4d h %4d font size : %d nb lines %d", w, h, font_size, len(lines))
        # left top right bottom
        im2= ImageOps.expand(im, border=(lr_borders, 0, lr_borders, b_border))
        draw: ImageDrawPIL= ImageDraw.Draw(im2)

        y= h + 2
        draw.rectangle([
            (2, y), 
            (r_w - 2, y + 2 + (len(lines) * (font_size+3)))
            ], outline=(255,255,255), width=1)
        for text in lines:
            draw.text((3,y), text, fill=(255,255,255), font=font)
            y+= font_size + 3
        return im2
            
    def _join_images(self, images: List[ImagePIL]):
        count= len(images)

        if count == 1:
            return images[0]
        
        rows, cols= CastingImageInfo._get_grid_size(len(images))       
        max_w= 0
        max_h= 0
        for i in range(count):
            w,h= images[i].size
            max_w= max(max_w, w)
            max_h= max(max_h, h)
            
        grid_w= max_w * cols
        grid_h= max_h * rows
        grid = Image.new('RGB', size=(grid_w, grid_h))

        im: ImagePIL
        for i, im in enumerate(images):
            grid.paste(im, box=(i%cols*max_w, i//cols*max_h))
        return grid
        
    def _tensor_to_pil(self, obj: Tensor) -> ImagePIL:
        dimensions= len(obj.size())
        batch_size= 1
        if dimensions == 4:
            batch_size= len(obj)
        logger.info("Convert Tensor to PIL. Tensor has %d dimensions. Batch size %d", dimensions, batch_size)
        if dimensions < 4:
            im: ImagePIL= CastingImageInfo._torch_to_pil(obj)
            return im
        
        rows, cols= CastingImageInfo._get_grid_size(batch_size)       
        images: List[ImagePIL]= []
        for i in range(batch_size):
            im: ImagePIL= CastingImageInfo._torch_to_pil(obj[i])
            images.append(im)
            
        return self._join_images(images=images)
    
    def is_ready(self) -> bool:
        return self._ready and self._path.is_file()

class CastThread(Thread):
    _chromecast: pychromecast.Chromecast= None
    
    def __init__(self, stop_event: Event, image_queue: Queue, config: CastConfiguration):
        Thread.__init__(self)
        logger.info("Init Cast Thread Config: %r", config)
        self.stop_event= stop_event
        self.queue= image_queue
        self.config= config
    
    def run(self):
        logger.info("Start Cast Thread")
        last_sent= None
        min_wait= 2
        last_id_live_preview: int= -1
        current_job: str= ""
        if self.config.cast_type != CastType.CHROMECAST:
            logger.critical("Cast type %s not supported.", self.config.cast_type.value)
            return
        while not self.stop_event.is_set():
            try:
                # Using timeout of 5 seconds to allow teardown within 5 seconds if
                # we request a stop but the queue is empty and no other objects come in
                img_info= self.queue.get(timeout=5)
                logger.info("Processing image")
                
                if self._chromecast is None:
                    if self.config.cast_type == CastType.CHROMECAST:
                        chromecasts, browser= pychromecast.get_listed_chromecasts(friendly_names=[self.config.device_name]) 
                        obj: pychromecast.Chromecast
                        for obj in chromecasts:
                            if obj.name == self.config.device_name:
                                logger.debug("Found device")
                                self._chromecast= obj
                                gr.Info(f"Connecting to {self.config.device_name}")
                                #Info App CC1AD845
                                break
                        else:
                            logger.warning("ChromeCast %s is unreachable, dropping image")
                            gr.Warning(f"Unable to connect to {self.config.device_name}")
                            continue
                self._chromecast.wait(timeout=5)
                casting_image= CastingImageInfo(image_info=img_info, config=self.config)
                if casting_image.is_ready():
                    if last_sent is not None:
                        while (datetime.now() - last_sent).total_seconds() < min_wait:
                            logger.debug("Wait, not %d seconds since last play", min_wait)
                            time.sleep(1)
                    logger.info("Casting %s", casting_image.url)
                    self._chromecast.play_media(url=casting_image.url, content_type=casting_image.mime_type)
                    last_sent= datetime.now()                
            except Empty as e:
                # Empty queue, check if live preview availabe
                #shared.state.id_live_preview != req.id_live_preview
                #shared.state.set_current_image()
                #logger.debug("Empty queue. State (%s) : (%r)", type(shared.state), shared.state)
                if (getattr(shared.opts, "cast_live_preview", False) == True):
                    state: State= shared.state
                    if (state.job != "" 
                        and (current_job != state.job or state.id_live_preview != last_id_live_preview)
                        and state.current_image is not None):
                        logger.debug("Casting a preview")
                        start_time= datetime.fromtimestamp(state.time_start)
                        messages=[f"Preview {state.id_live_preview}", f"Job : {state.job}"]
                        logger.debug(messages)
                        info= ImageInfo(ImageType.PIL, obj= state.current_image, creation_date=start_time, message= messages)
                        current_job= state.job
                        last_id_live_preview= state.id_live_preview
                        self.queue.put_nowait(info)
            except Exception as e:
                gr.Warning('Error casting image')
                logger.exception("Error processing image")
        logger.warning("Cast thread ended, stop event received")
        if self._chromecast is not None:
            gr.Warning(f"Disconnect from {self.config.device_name}")
            self._chromecast.disconnect()
            