# ASMR FreeCAD
just some resources and macros for designing junk in FreeCAD.

## Forking an existing Post-Processor Script
there are a handful of post-processors that ship by default with FreeCAD. on debian they can be found here (assuming an apt install):
``` shell
/usr/share/freecad/Mod/Path/PathScripts/post/
```
you can copy any file and modify it to get customized behavior.

## Adding CNC Post-Processor Scripts
symlink the post-processor of interest to the `~/.FreeCAD/Macro/` directory

## Resources
* [Sketcher Scripting Basics, very helpful](https://wiki.freecadweb.org/Sketcher_scripting)
* [FreeCAD Class Docs](https://freecad.github.io/SourceDoc/annotated.html)
* [PySide Docs for QT Gui Stuff](https://srinikom.github.io/pyside-docs/contents.html)
