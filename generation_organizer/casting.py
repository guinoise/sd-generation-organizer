from dataclasses import dataclass
from enum import Enum
import pathlib
from typing import Union, List
from datetime import datetime

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

@dataclass
class ImageInfo:
    image_type: ImageType
    obj: any
    creation_date: datetime
    message: Union[str, List[str], None]