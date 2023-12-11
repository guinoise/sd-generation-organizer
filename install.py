import launch

mods= ["SQLAlchemy", "Pillow", "sqlite4", "pathlib", "pychromecast"]

for m in mods:
    if not launch.is_installed(m):
        launch.run_pip("install {}".format(m), f"requirements for sd-webui-generation-organizer : {m}")
