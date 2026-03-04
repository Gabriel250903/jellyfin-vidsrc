import os
import sys
import re
import subprocess


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def sanitize_path(text):
    return re.sub(r'[\/*?:"<>|]', "", text).strip()


def notify(title, msg):
    try:
        ps_script = f"""
        [reflection.assembly]::loadwithpartialname('System.Windows.Forms') | Out-Null
        $obj = New-Object System.Windows.Forms.NotifyIcon
        $obj.Icon = [System.Drawing.Icon]::ExtractAssociatedIcon((Get-Process -id $pid).Path)
        $obj.BalloonTipTitle = '{title}'
        $obj.BalloonTipText = '{msg}'
        $obj.Visible = $True
        $obj.ShowBalloonTip(5000)
        """
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script], capture_output=True
        )
    except:
        pass
