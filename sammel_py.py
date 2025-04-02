# -*- coding: utf-8 -*-
#
# This file is part of VGSync.
#
# Copyright (C) 2025 by Bernd Eller
#
# VGSync is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# VGSync is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with VGSync. If not, see <https://www.gnu.org/licenses/>.
#
import os

# Pfad zum Verzeichnis
directory = "."

# Ausgabedatei
output_file = "alle_dateien.txt"
trenner = "```"

with open(output_file, "w", encoding="utf-8") as outfile:
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                #outfile.write(f"Datei: {filepath}\n")
                with open(filepath, "r", encoding="utf-8") as infile:
                    outfile.write(infile.read())
                outfile.write(f"\n{trenner}\n")
                
print(f"Fertig! Alle Dateien wurden in {output_file} geschrieben.")

