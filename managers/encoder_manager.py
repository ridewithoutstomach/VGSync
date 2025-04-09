# -*- coding: utf-8 -*-
#
# managers/encoder_manager.py
#
# Dies ist eine Integration deines Codes aus xfade6_2.py in
# ein Qt-Dialogfenster (EncoderDialog). Vor dem Start fragt
# es per Dateiauswahl den finalen Ausgabe-Pfad ab und überschreibt
# c["final_output"]. Danach läuft deine XFade-Logik wie gehabt.
#
# Alle print()-Ausgaben erscheinen in QPlainTextEdit. Der Code in
# xfade_main() und den Funktionen ist 1:1 übernommen.

import os
import sys
import re
import json
import subprocess
import tempfile
import shutil

from PySide6.QtCore import QSettings, QObject, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QPlainTextEdit, QPushButton,
    QApplication, QFileDialog
)

##############################################################################
# 1) Hilfsklasse zum Abfangen von print-Ausgaben
##############################################################################

import contextlib

class _StringStream:
    """
    Wenn wir stdout dorthin umleiten, ruft jede 'write(text)' => callback(text).
    """
    def __init__(self, callback):
        self._callback = callback
    def write(self, text):
        self._callback(text)
    def flush(self):
        pass


##############################################################################
# 2) ALLE FUNKTIONEN AUS xfade6_2.py UNVERÄNDERT  (außer 'main' heißt jetzt xfade_main)
##############################################################################

def get_or_create_encoder_temp_dir():
    s = QSettings("VGSync","VGSync")
    key = "encoderTempDir"
    current= s.value(key,"",type=str)
    if not current:
        default_path= os.path.join(tempfile.gettempdir(),"my_vgsync_encoder")
        s.setValue(key,default_path)
        current = default_path
    os.makedirs(current,exist_ok=True)
    return current

def clear_encoder_temp_dir():
    tdir = get_or_create_encoder_temp_dir()
    try:
        shutil.rmtree(tdir)
    except:
        pass
    os.makedirs(tdir,exist_ok=True)
    return tdir

gpu_map_nvidia = {
    "ultrafast": "fast",
    "superfast": "fast",
    "veryfast":  "fast",
    "faster":    "medium",
    "fast":      "hp",
    "medium":    "default",
    "slow":      "hq",
    "slower":    "hq",
    "veryslow":  "llhq"
}
gpu_map_amd = {
    "ultrafast": "speed",
    "superfast": "speed",
    "veryfast":  "speed",
    "faster":    "balanced",
    "fast":      "balanced",
    "medium":    "balanced",
    "slow":      "quality",
    "slower":    "quality",
    "veryslow":  "quality"
}
gpu_map_intel = {
    "ultrafast": "veryfast",
    "superfast": "veryfast",
    "veryfast":  "veryfast",
    "faster":    "fast",
    "fast":      "fast",
    "medium":    "medium",
    "slow":      "slow",
    "slower":    "slower",
    "veryslow":  "slower"
}

def map_preset_for_gpu(user_preset, hw_encode):
    if not user_preset:
        return None
    up= user_preset.lower()
    hw_lc= (hw_encode or "").lower()
    if hw_lc.startswith("nvidia_"):
        return gpu_map_nvidia.get(up,"default")
    elif hw_lc.startswith("amd_"):
        return gpu_map_amd.get(up,"balanced")
    elif hw_lc.startswith("intel_"):
        return gpu_map_intel.get(up,"medium")
    return user_preset

def determine_encoder(cpu_encoder="libx265", hw_encode=None):
    if not hw_encode or hw_encode.lower()=="none":
        return cpu_encoder,"cpu"
    hw_map={
        "nvidia_h264":"h264_nvenc",
        "nvidia_hevc":"hevc_nvenc",
        "amd_h264":"h264_amf",
        "amd_hevc":"hevc_amf",
        "intel_h264":"h264_qsv",
        "intel_hevc":"hevc_qsv"
    }
    val= hw_map.get(hw_encode.lower(),"")
    if not val:
        print(f"[WARN] unknown hw_encode={hw_encode}, fallback CPU {cpu_encoder}")
        return cpu_encoder,"cpu"
    return val,"gpu"

def get_cpu_closedgop_params(enc_name="libx265"):
    if enc_name=="libx264":
        return ["-x264-params","bframes=0:scenecut=0","-g","15","-keyint_min","15"]
    else:
        return ["-x265-params","bframes=0:no-open-gop=1:scenecut=0","-g","15","-keyint_min","15"]

def get_gpu_closedgop_params(hw_encode):
    return ["-bf","0","-g","30"]

def clamp_crf(crf_val):
    if crf_val<0: crf_val=0
    if crf_val>51: crf_val=51
    return crf_val

def build_scale_filter(width):
    if width is None:
        return None
    return f"scale={width}:-2"

def encode_closedgop(
    concat_file,
    outname,
    encoder="libx265",
    hw_encode=None,
    fps=None,
    crf=None,
    width=None,
    preset=None
):
    enc_name, mode = determine_encoder(encoder, hw_encode)
    real_preset = preset
    if mode=="gpu":
        real_preset= map_preset_for_gpu(preset, hw_encode)

    filter_str= build_scale_filter(width)
    cmd=[
        "ffmpeg","-hide_banner","-y",
        "-f","concat","-safe","0",
        "-i", concat_file,
        "-an"
    ]
    if crf is None:
        crf=23

    if mode=="cpu":
        p_extra= get_cpu_closedgop_params(enc_name)
        cmd+= ["-c:v", enc_name, "-crf", str(crf)]
        if real_preset:
            cmd+= ["-preset", real_preset]
        cmd+= p_extra
        print(f"[DEBUG] CPU => CRF={crf}")
    else:
        qv= clamp_crf(crf)
        p_extra= get_gpu_closedgop_params(hw_encode)
        cmd+=["-c:v", enc_name,
              "-rc:v","vbr_hq",
              "-cq", str(qv)]
        if real_preset:
            cmd+= ["-preset", real_preset]
        cmd+= p_extra
        print(f"[DEBUG] GPU => vbr_hq + -cq={qv}")

    if fps:
        cmd+= ["-r", str(fps)]
    if filter_str:
        cmd+= ["-vf", filter_str]

    cmd+= [outname]
    print("ENCODE_CLOSEDGOP:", " ".join(cmd))
    subprocess.run(cmd, check=True)


import re
def get_keyframes(src):
    print(f"\nIndexing Keyframes in {src} ...")
    pattern= re.compile(r'"best_effort_timestamp_time"\s*:\s*"')
    cmd=[
        "ffprobe","-hide_banner",
        "-select_streams","v:0",
        "-skip_frame","nokey",
        "-show_frames",
        "-show_entries","frame=best_effort_timestamp_time",
        "-print_format","json",
        "-i", src
    ]
    p= subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    lines=[]
    count=0
    while True:
        line= p.stdout.readline()
        if not line and p.poll() is not None:
            break
        if line:
            lines.append(line)
            if pattern.search(line):
                count+=1
                print(f"\rIndexing Keyframes: {count}",end='',flush=True)
    p.wait()
    print()
    data= json.loads("".join(lines))
    frames_data= data.get("frames",[])
    times=[]
    for fr in frames_data:
        t= float(fr.get("best_effort_timestamp_time","0"))
        times.append(t)
    times.sort()
    print(f"Total Keyframes found: {len(times)}\n")
    return times

def get_kf_le(kf_list,t):
    if not kf_list:
        return 0.0
    best=kf_list[0]
    for k in kf_list:
        if k<=t:
            best=k
        else:
            break
    return best

def get_kf_ge(kf_list,t):
    if not kf_list:
        return t
    for k in kf_list:
        if k>=t:
            return k
    return kf_list[-1]

def copy_cut(src,start,end,outfile):
    dur= end-start
    if dur<=0:
        raise ValueError("invalid cut dur => start={start},end={end}")
    cmd=[
        "ffmpeg","-hide_banner","-y",
        "-ss",f"{start:.3f}",
        "-i",src,
        "-t",f"{dur:.3f}",
        "-map","0:v:0",
        "-c","copy",
        outfile
    ]
    print("COPY_CUT:", " ".join(cmd))
    subprocess.run(cmd,check=True)

def crossfade_2(
    inA,inB,outname,
    encoder="libx265",
    hw_encode=None,
    crf=23,
    fps=None,width=None,preset=None,
    overlap=2
):
    enc_name, mode= determine_encoder(encoder,hw_encode)
    real_preset= preset
    if mode=="gpu":
        real_preset= map_preset_for_gpu(preset,hw_encode)

    filter_complex=[]
    if width:
        filter_complex.append(f"[0:v]scale={width}:-2,format=yuv420p[v0]")
        filter_complex.append(f"[1:v]scale={width}:-2,format=yuv420p[v1]")
    else:
        filter_complex.append("[0:v]format=yuv420p[v0]")
        filter_complex.append("[1:v]format=yuv420p[v1]")
    filter_complex.append(f"[v0][v1]xfade=transition=fade:duration={overlap}:offset=0[vout]")
    flt=";".join(filter_complex)

    cmd=[
        "ffmpeg","-hide_banner","-y",
        "-i",inA,
        "-i",inB,
        "-filter_complex",flt,
        "-map","[vout]"
    ]

    if mode=="cpu":
        p_extra= get_cpu_closedgop_params(enc_name)
        cmd+= ["-c:v", enc_name, "-crf", str(crf)]
        if real_preset:
            cmd+= ["-preset", real_preset]
        cmd+= p_extra
        print(f"[DEBUG] CROSSFADE => CPU => CRF={crf}")
    else:
        qv= clamp_crf(crf)
        p_extra= get_gpu_closedgop_params(hw_encode)
        cmd+= ["-c:v", enc_name, "-rc","vbr_hq", "-cq", str(qv)]
        if real_preset:
            cmd+= ["-preset", real_preset]
        cmd+= p_extra
        print(f"[DEBUG] CROSSFADE => GPU => -cq={qv}")

    if fps:
        cmd+=["-r",str(fps)]
    cmd+=["-pix_fmt","yuv420p","-an", outname]
    print("CROSSFADE_2:", " ".join(cmd))
    subprocess.run(cmd,check=True)

def final_concat_copy(parts,outfile):
    tmp_list= os.path.splitext(outfile)[0]+"_concat.txt"
    with open(tmp_list,"w",encoding="utf-8") as f:
        for p in parts:
            abspath= os.path.abspath(p)
            f.write(f"file '{abspath}'\n")

    cmd=[
        "ffmpeg","-hide_banner","-y",
        "-f","concat","-safe","0",
        "-i", tmp_list,
        "-map","0:v:0",
        "-c","copy",
        outfile
    ]
    print("FINAL CONCAT COPY:", " ".join(cmd))
    subprocess.run(cmd,check=True)
    os.remove(tmp_list)

def _build_overlay_input_args(img):
    ext= os.path.splitext(img.lower())[1]
    if ext in (".png",".jpg",".jpeg",".bmp"):
        return ["-loop","1","-f","image2","-i", img]
    elif ext==".gif":
        return ["-stream_loop","-1","-i", img]
    else:
        return ["-i", img]

def overlay_segment_encode(
    in_segment,out_segment,
    overlay_image,
    fade_in=1.0,fade_out=1.0,
    seg_duration=None,scale=1.0,x=0,y=0,
    encoder="libx265",hw_encode=None,crf=23,
    fps=None,preset=None,width=None
):
    if seg_duration is None:
        cmd_dur=[
            "ffprobe","-v","error",
            "-show_entries","format=duration",
            "-of","default=noprint_wrappers=1:nokey=1",
            in_segment
        ]
        rr=subprocess.run(cmd_dur,capture_output=True,text=True,check=True)
        seg_duration= float(rr.stdout.strip())

    fade_out_start= seg_duration - fade_out
    if fade_out_start<0:
        fade_out_start=0

    filter_complex=[]
    chain=[]
    chain.append("format=rgba")
    if fade_in>0:
        chain.append(f"fade=t=in:st=0:d={fade_in:.3f}:alpha=1")
    if fade_out>0:
        chain.append(f"fade=t=out:st={fade_out_start:.3f}:d={fade_out:.3f}:alpha=1")
    chain.append(f"scale=iw*{scale}:ih*{scale}:force_original_aspect_ratio=decrease")

    chain_str=",".join(chain)
    filter_complex.append(f"[1:v]{chain_str}[ov1]")

    base_in="[vbase]"
    if width:
        filter_complex.append(f"[0:v]scale={width}:-2,format=yuv420p[vbase]")
    else:
        filter_complex.append("[0:v]format=yuv420p[vbase]")
    x_str= str(x)
    y_str= str(y)
    overlay_str= f"{base_in}[ov1]overlay=x={x_str}:y={y_str}:format=auto[vout]"
    filter_complex.append(overlay_str)

    fc_str= ";".join(filter_complex)

    overlay_input_args= _build_overlay_input_args(overlay_image)
    cmd=[
        "ffmpeg","-hide_banner","-y",
        "-i", in_segment
    ]+ overlay_input_args + [
        "-filter_complex", fc_str,
        "-map","[vout]",
        "-t", f"{seg_duration:.3f}"
    ]

    enc_name, mode= determine_encoder(encoder, hw_encode)
    real_preset= preset
    if mode=="gpu":
        real_preset= map_preset_for_gpu(preset,hw_encode)

    if mode=="cpu":
        p_extra= get_cpu_closedgop_params(enc_name)
        cmd+= ["-c:v", enc_name, "-crf", str(crf)]
        if real_preset:
            cmd+= ["-preset", real_preset]
        cmd+= p_extra
        print(f"[DEBUG] overlay => CPU => CRF={crf}")
    else:
        qv= clamp_crf(crf)
        p_extra= get_gpu_closedgop_params(hw_encode)
        cmd+= ["-c:v", enc_name, "-rc","vbr_hq","-cq", str(qv)]
        if real_preset:
            cmd+= ["-preset", real_preset]
        cmd+= p_extra
        print(f"[DEBUG] overlay => GPU => -cq={qv}")

    if fps:
        cmd+=["-r",str(fps)]
    cmd+=["-pix_fmt","yuv420p","-an", out_segment]

    print("OVERLAY_SEGMENT_ENCODE:", " ".join(cmd))
    subprocess.run(cmd,check=True)

def build_segments_with_skip_and_overlay(
    merged_file,kf_list,total_duration,
    skip_instructions,overlay_instructions,
    encoder="libx265",hw_encode=None,crf=23,fps=None,width=None,preset=None
):
    events=[]
    for triple in skip_instructions:
        s,e,o= triple
        ev={"type":"skip","start":float(s),"end":float(e),"overlap":float(o)}
        events.append(ev)
    for ov in overlay_instructions:
        ev={
          "type":"overlay",
          "start": float(ov["start"]),
          "end": float(ov["end"]),
          "fade_in": float(ov.get("fade_in",1.0)),
          "fade_out": float(ov.get("fade_out",1.0)),
          "image": ov["image"],
          "scale": float(ov.get("scale",1.0)),
          "x": ov.get("x",0),
          "y": ov.get("y",0)
        }
        events.append(ev)

    events.sort(key=lambda x: x["start"])
    temp_dir= get_or_create_encoder_temp_dir()
    segments=[]
    out_count=1
    current_pos=0.0

    for ev in events:
        t1= ev["start"]
        t2= ev["end"]
        if t2<= t1:
            continue
        if t1> current_pos:
            seg_start= get_kf_le(kf_list,current_pos)
            seg_end= get_kf_le(kf_list,t1)
            if seg_end>seg_start:
                part_out= os.path.join(temp_dir,f"part_{out_count:02d}_{int(seg_start)}_{int(seg_end)}.mp4")
                copy_cut(merged_file,seg_start,seg_end,part_out)
                segments.append(part_out)
                out_count+=1

        if ev["type"]=="skip":
            overlap= ev["overlap"]
            ovA_start= get_kf_ge(kf_list,t1)
            ovA_end= get_kf_le(kf_list,t1+overlap)
            if ovA_end<ovA_start:
                ovA_end=ovA_start
            ovA_file= os.path.join(temp_dir,f"skipA_{out_count:02d}_{int(t1)}.mp4")
            copy_cut(merged_file,ovA_start,ovA_end,ovA_file)

            ovB_start= get_kf_ge(kf_list,t2)
            ovB_end= get_kf_le(kf_list,t2+overlap)
            if ovB_end<ovB_start:
                ovB_end=ovB_start
            ovB_file= os.path.join(temp_dir,f"skipB_{out_count:02d}_{int(t2)}.mp4")
            copy_cut(merged_file,ovB_start,ovB_end,ovB_file)

            xf_out= os.path.join(temp_dir,f"skipX_{out_count:02d}_{int(t1)}_{int(t2)}.mp4")
            crossfade_2(
                inA=ovA_file, inB=ovB_file, outname=xf_out,
                encoder=encoder,hw_encode=hw_encode,crf=crf,
                fps=fps,width=width,preset=preset,
                overlap=overlap
            )
            segments.append(xf_out)
            out_count+=1
            current_pos= t2+ overlap

        elif ev["type"]=="overlay":
            fade_in= ev["fade_in"]
            fade_out= ev["fade_out"]
            ov_img= ev["image"]
            sc= ev["scale"]
            xx= ev["x"]
            yy= ev["y"]
            seg_start= get_kf_ge(kf_list,t1)
            seg_end= get_kf_le(kf_list,t2)
            if seg_end< seg_start:
                seg_end= seg_start
            in_cut= os.path.join(temp_dir,f"ov_in_{out_count:02d}_{int(t1)}.mp4")
            copy_cut(merged_file,seg_start,seg_end,in_cut)
            out_cut= os.path.join(temp_dir,f"ov_out_{out_count:02d}_{int(t1)}_{int(t2)}.mp4")
            seg_dur= seg_end- seg_start
            overlay_segment_encode(
                in_segment=in_cut,out_segment=out_cut,
                overlay_image=ov_img,fade_in=fade_in,fade_out=fade_out,
                seg_duration=seg_dur,scale=sc,x=xx,y=yy,
                encoder=encoder,hw_encode=hw_encode,crf=crf,
                fps=fps,preset=preset,width=None
            )
            segments.append(out_cut)
            out_count+=1
            current_pos= t2

    if current_pos< total_duration:
        seg_start= get_kf_ge(kf_list,current_pos)
        seg_end= get_kf_le(kf_list,total_duration)
        if seg_end>seg_start:
            final_out= os.path.join(temp_dir,f"final_{out_count:02d}_{int(seg_start)}_{int(seg_end)}.mp4")
            copy_cut(merged_file,seg_start,seg_end,final_out)
            segments.append(final_out)
            out_count+=1

    return segments

##############################################################################
# 3) Deine alte main() heißt jetzt xfade_main(cfg_path)
#    (1:1 Kopie, nur sys.argv weg)
##############################################################################

def xfade_main(cfg_path):
    """
    1:1 aus xfade6_2.py: Liest config JSON von cfg_path,
    führt merges, crossfade, overlays etc. durch.
    """
    with open(cfg_path,"r",encoding="utf-8") as f:
        c= json.load(f)

    videos= c["videos"]
    skip_list= c.get("skip_instructions",[])
    overlay_list= c.get("overlay_instructions",[])
    merged_out= c["merged_output"]
    final_out= c["final_output"]

    hw_encode= c.get("hardware_encode","none")
    encoder= c.get("encoder","libx265")
    crf= c.get("crf",23)
    fps= c.get("fps",30)
    width= c.get("width",None)
    preset= c.get("preset",None)

    tdir= clear_encoder_temp_dir()
    print("[INFO] TempDir =>", tdir)

    base_name= os.path.basename(merged_out)
    merged_path= os.path.join(tdir, base_name)

    concat_txt= os.path.join(tdir,"concat_input.txt")
    with open(concat_txt,"w",encoding="utf-8") as f2:
        for v in videos:
            abspath= os.path.abspath(v)
            f2.write(f"file '{abspath}'\n")

    encode_closedgop(
        concat_file= concat_txt,
        outname= merged_path,
        encoder= encoder,
        hw_encode= hw_encode,
        fps= fps,
        crf= crf,
        width= width,
        preset= preset
    )

    cmd_dur=[
        "ffprobe","-v","error",
        "-show_entries","format=duration",
        "-of","default=noprint_wrappers=1:nokey=1",
        merged_path
    ]
    rr= subprocess.run(cmd_dur,capture_output=True,text=True,check=True)
    total_dur= float(rr.stdout.strip())

    kf= get_keyframes(merged_path)

    parted= build_segments_with_skip_and_overlay(
        merged_file= merged_path,
        kf_list= kf,
        total_duration= total_dur,
        skip_instructions= skip_list,
        overlay_instructions= overlay_list,
        encoder= encoder,
        hw_encode= hw_encode,
        crf= crf,
        fps= fps,
        width= width,
        preset= preset
    )
    final_concat_copy(parted, final_out)

    print("\n=== DONE ===")
    print("Ergebnis =>", final_out)
    print("CRF/GPU => CPU => -crf | GPU => -rc vbr_hq -cq <CRF>.\n")


##############################################################################
# 4) Ein QDialog, das xfade_main() aufruft + Dateiauswahl
##############################################################################

class EncoderDialog(QDialog):
    """
    1) Fragt via QFileDialog den final_output ab (überschreibt JSON-Field).
    2) Ruft xfade_main(json_path) auf, leitet print-Ausgabe ins TextEdit.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("XFade6 Encoding")
        layout = QVBoxLayout(self)

        self.text_edit = QPlainTextEdit(self)
        self.text_edit.setReadOnly(True)
        layout.addWidget(self.text_edit)

        btn_close = QPushButton("Close", self)
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close)

        self.setLayout(layout)
        self.resize(800, 600)

    def run_encoding(self, json_path: str):
        """
        1) JSON laden
        2) Dateiauswahl-Fenster => final_out
        3) c["final_output"] = final_out
        4) xfade_main(...) => print-Ausgaben => text_edit
        """
        # 1) JSON laden (so können wir c anpassen, bevor xfade_main sie nutzt)
        with open(json_path,"r",encoding="utf-8") as f:
            c= json.load(f)

        # 2) Dateiauswahlfenster => Der Benutzer wählt final_out
        proposed = c.get("final_output","final_out.mp4")
        chosen, _ = QFileDialog.getSaveFileName(
            self,
            "Choose final output",
            proposed,
            "Video Files (*.mp4 *.mov *.mkv *.avi)"
        )
        if not chosen:
            # User hat abgebrochen
            self.text_edit.appendPlainText("[ABBRUCH] Keine Zieldatei gewählt.\n")
            return

        # => final_out überschreiben
        c["final_output"] = chosen

        # 3) JSON neu speichern => xfade_main() liest dieselbe config ein
        temp_json = os.path.join(tempfile.gettempdir(), "xfade_temp.json")
        with open(temp_json, "w", encoding="utf-8") as f2:
            json.dump(c, f2, indent=2)

        # 4) print-Ausgaben umleiten => text_edit
        stream = _StringStream(self._on_new_text)
        with contextlib.redirect_stdout(stream):
            try:
                xfade_main(temp_json)
            except Exception as e:
                print(f"\n[ERROR] {e}")

    def _on_new_text(self, text: str):
        """
        Callback pro print-Ausgabe.
        """
        # an Textfeld anhängen
        self.text_edit.moveCursor(QTextCursor.End)
        self.text_edit.insertPlainText(text)
        self.text_edit.moveCursor(QTextCursor.End)
        QApplication.processEvents()
