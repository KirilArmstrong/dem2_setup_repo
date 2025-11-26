# Demonstrator 2

Repository for the 3D Label Free Demonstrator 2 setup.

### Motivation:
- Control devices.
	- Sweeping laser source.
	- Camera acquisition.
	- Sample stage.
- Synchronise sweep source with camera acquisition.
- Image data IO.
- Automate B-scan.

### Documentation Wiki

Documentation for the project can be found [here](https://github.com/myleneamstutz/3d_label_free_dem_2/blob/dev/dem2_doc_vault/Welcome.md).

#### Structure

```
__root__
├ config (git untracked)
├ data (git untracked)
├ dem2_doc_vault (documentation vault)
├ examples
├ logs (git untracked)
├ src
│ └ dem_2_3d_label_free (project)
│   ├ dem2_common (sofware package)
│   │ └ dem2_<name>.py (file name convention)
│   │   └ Dem2<class name> (class name convention)
│   ├ dem2_components (hardware control package)
│   ├ dem2_devices (hardware package)
│   ├ __globals__.py (global variables)
│   └ t.b.d.
├ templates
│ └ config.template.yml (default config file)
├ .gitignore
└ README.md
```