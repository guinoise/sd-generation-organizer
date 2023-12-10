[!WARNING] WORK IN PROGRESS [!WARNING]

# Generation Organizer
In short : Stable Diffusion extension to manage and organize generations.

This extension is code to provide a way to organize, manage and refine
our generated images from stable-diffusion-webui. 

The project started from personnel needs and some features are inspired from
other extensions. 

# Main features
## Database storage and metadata
All generated images are parsed and indexed into a database.

Data are extracted and stored into the database.

Some metadata are added to the database and/or image metadata. For example the
metadata for date creation of the image (which should be the generation datetime) is not stored inside the PNG metada. This extension will add this metadata.

## Casting capabilities
I started to create an extension that allow me to cast the images while
they are generated. But the lack of capabalities to organized the results from
stable diffusion was a deal breaker at some point and rendered the extension not so usefull. So I decided to combined the efforts in this extension instead.

# Work in progress / TODO
- [ ] UI Tab
- [ ] UI Options
- [ ] Casting capabilities
    - Devices
        - [ ] Chromecast
        - [ ] AirPlay
    - Options 
        - [ ] Cast rendering images
        - [ ] Cast selected
        - [ ] Create a gallery
- [ ] Gallery of outputs
- [ ] Queue manager
- [ ] Diff between generated inputs (parameters)
- [ ] Tag images
- [ ] Tag/identified NSFW content
