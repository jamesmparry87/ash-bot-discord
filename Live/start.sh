#!/bin/bash
cd Live
which python3 && python3 --version
python3 -m pip install --upgrade discord.py
python3 -m pip show discord.py
python3 bot_modular.py