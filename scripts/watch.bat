@REM Launch the watcher script to monitor the specified directory for new markdown files and generate descriptions for them.
@echo off

set project_root=%~dp0..
@REM resolve the absolute path of the project root directory
for %%I in ("%project_root%") do set project_root=%%~fI

cd /d "%project_root%"
pythonw -m uv_agent_workspace.watch

