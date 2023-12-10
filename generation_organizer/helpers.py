from modules import shared, scripts
import pathlib
import logging
from logging.handlers import RotatingFileHandler


## Directory variables and early variables
# Some are required for logger, setting here
# Set other variables in block Variables
base_dir: pathlib.Path= pathlib.Path(scripts.basedir())
data_path: pathlib.Path= pathlib.Path(shared.data_path)
log_dir: pathlib.Path= base_dir.joinpath("log")
temp_dir: pathlib.Path= data_path.joinpath("tmp")

## INIT Logger
if not log_dir.exists():
    print ("Creating log directory %s" % log_dir.resolve())
    log_dir.mkdir(parents=True)

log_file= log_dir.joinpath("generation_organizer.log")
fh = RotatingFileHandler(log_file, mode='a', maxBytes=100*1024*1024, backupCount=5)

fh.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s [%(levelname)-9s][%(name)-20s] %(message)s')
fh.setFormatter(formatter)
logger= logging.getLogger("organizer")
logger.addHandler(fh)

if shared.cmd_opts.loglevel:
    if shared.cmd_opts.loglevel.upper() == "DEBUG":
        logger.setLevel(logging.DEBUG)
    elif shared.cmd_opts.loglevel.upper() == "INFO":
        logger.setLevel(logging.INFO)
    elif shared.cmd_opts.loglevel.upper() in ["WARN", "WARNING"]:
        logger.setLevel(logging.WARNING)
    elif shared.cmd_opts.loglevel.upper() == "ERROR":
        logger.setLevel(logging.ERROR)
    elif shared.cmd_opts.loglevel.upper() == "CRITICAL":
        logger.setLevel(logging.CRITICAL)
    else:
        logger.setLevel(logging.INFO)    
        logger.critical("ERROR SETTING Debug level, value %r could not be parsed, defaulting to INFO", shared.cmd_opts.loglevel)
else:
    logger.setLevel(logging.INFO)

logger.setLevel(logging.DEBUG)
# End logger
