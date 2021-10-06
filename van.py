import pyvan

OPTIONS = {
  "main_file_name": "main.py",
  "show_console": True,
  "use_existing_requirements": True,
  "extra_pip_install_args": [],
  "python_version": None,
  "use_pipreqs": False,
  "install_only_these_modules": [],
  "exclude_modules": [],
  "include_modules": [],
  "path_to_get_pip_and_python_embedded_zip": "",
  "build_dir": "dist",
  "pydist_sub_dir": "pydist",
  "source_sub_dir": "",
  "icon_file": None,
}

pyvan.build(**OPTIONS)
