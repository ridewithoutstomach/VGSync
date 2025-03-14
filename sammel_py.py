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

