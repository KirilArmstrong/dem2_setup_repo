# Project Structure

## Requirements

The following packages are required for the `dem_2_3d_label_free` project to work.
- [Zeiss Conda Environment](https://python-community.zeiss.org/quick-start/python-with-anaconda.html) - Contains all default packages, and adds necessary repositories for any additional packages.
	- [zeiss_helpers](https://python-community.zeiss.org/conda/p/jl4conda/zeiss_helpers)
- Additional Sources
	- [ximea API](https://www.ximea.com/support/wiki/apis/APIs)
	- ZEISS MTB API
### Additional Sources
After installing the additional software packages, ensure you add them as sources.
#### VS Code
In your `~/.vscode/settings.json` ensure the following is present:
```json
{
	// ... other settings
	
	"python.analysis.extraPaths": [
		"path/to/folder/containing/ximea/API/Python/v3/ximea",
		"path/to/folder/containing/mtbapi"
	],
	"python.autoComplete.extraPaths": [
		"path/to/folder/containing/ximea/API/Python/v3/ximea",
		"path/to/folder/containing/mtbapi"
	]
	
	// ... other settings
}
```

> ⚠️ Note
> 
> JSON doesn't support comments. Don't include them please.

#### PyCharm
Add the following directories as source roots in `File > Settings > Project Structure > + Add Content Root`.
- `path/to/folder/containing/ximea/API/Python/v3/ximea`
- `path/to/folder/containing/mtbapi`

## File Structure

The Structure is as follows:
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
│   └ __globals__.py (global variables)  
├ templates  
│ └ config.template.yml (default config file) 
├ tests (git untracked)
├ .gitignore  
└ README.md  
```

Source files should be placed in the `/src` directory within the project `dem_2_3d_label_free` in its respective package.

Example scripts that **should be git tracked** should be placed in the `/examples` directory.

Test scripts that should **not be git tracked** should be placed in the `/tests` directory.

Template configs and `.yml` files that **should be git tracked** should be placed in the `/templates` directory.

Documentation files should be placed in `/dem2_doc_vault` and should be `.md` (markdown) files. This ensure compatibility with the [Obsidian](https://obsidian.md/) software for documentation organisation.

See [[Packages]](https://github.com/myleneamstutz/3d_label_free_dem_2/blob/dev/dem2_doc_vault/Packages.md) for package structure and documentation.

### Git Tracking

Source, documentation, and template files should be the only files tracked. Test, data, or config files, unless for example purposes, should not be tracked. Directory or file omission can be done in the `.gitignore` file. 

### Conventions

**File names** should have the prefix `dem2_`, such as `dem2_helpers.py`.

**Class names** should have the prefix `Dem2`, such as `class Dem2SystemCalculator()`.

---

Tags: # | Quick Links: [[Home]](https://github.com/myleneamstutz/3d_label_free_dem_2/blob/dev/dem2_doc_vault/Home.md)

---
