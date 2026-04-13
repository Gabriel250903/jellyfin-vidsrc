import os
import sys
import re
import subprocess


def resource_path(relative_path):
    base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base_path, relative_path)


def sanitize_path(text):
    return re.sub(r'[\/*?:"<>|]', "", text).strip()


def notify(title, msg):
    try:
        from win11toast import toast

        toast(title, msg, app_id="VidSrc Jellyfin")
        return
    except ImportError:
        pass

    try:
        ps_script = f"""
        $title = "{title}"
        $msg = "{msg}"
        $appId = "VidSrc Jellyfin"
        
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
        
        $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
        $xml = [Windows.Data.Xml.Dom.XmlDocument]::new()
        $xml.LoadXml($template.GetXml())
        
        $textNodes = $xml.GetElementsByTagName('text')
        $textNodes.Item(0).AppendChild($xml.CreateTextNode($title)) | Out-Null
        $textNodes.Item(1).AppendChild($xml.CreateTextNode($msg)) | Out-Null
        
        $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
        """
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script], capture_output=True
        )
    except:
        pass
