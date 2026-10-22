# -*- coding: utf-8 -*-
"""A page of terms and conditions, drawn so it can be checked every build.

Six paragraphs came back where the document has fourteen. Every heading
was glued to the front of the paragraph it introduced, 3.8.1 to 3.8.4 were
mashed into one twelve-hundred-character block, and an engine handed that
much numbered text at once stopped translating and started editing it —
it lifted the clause numbers out to the end of the paragraph and wrote
"[number] months" where the contract said twenty-four.

None of that was a regression. The corpus was two newsletters and nine
synthetic pages of running prose; it had never contained a document that
numbers itself, so nothing ever asked whether one worked. It does now.

Writes the page and, beside it, the paragraph each drawn line belongs to,
so a checker can say how many of the document's own paragraphs came back
whole rather than only whether anything overlapped.

    python tools/legalpage.py tests/pages
"""
import sys, json
sys.path.insert(0, "/home/claude/Squint")
from PIL import Image, ImageDraw, ImageFont

W_PT, H_PT = 1263, 1650          # the shape of his page
SCALE = 1.5                      # his display reports 150%
W, H = int(W_PT * SCALE), int(H_PT * SCALE)

def font(size, bold=False):
    for name in (("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),):
        for base in ("/usr/share/fonts/truetype/dejavu/",):
            try:
                return ImageFont.truetype(base + name, size)
            except Exception:
                pass
    return ImageFont.load_default()

BODY = 25
HEAD = 25

DOC = [
    ("right", "Vertragsnummer 408939645", False),
    ("right", "Seite 6/6", False),
    ("gap", 18, None),
    ("head", "3.5 Online-Kommunikation", True),
    ("para", "3.5.1 OnlinevertragWird der Vertrag online geschlossen bzw. erteilt der Kunde den Auftrag zur Strom- und/oder Gaslieferung online über das Internet, schließt der Onlinevertrag die Nutzung des Serviceportals Mein E.ON sowie die Online-Kommunikation gemäß dieser Ziffer ein. Unter Onlinevertrag fallen Verträge, bei denen die Auftragserteilung des Kunden über eine Website (öffentlich zugänglich oder passwortgeschützt mit Log-In), über eine App (wie z.B. Mein E.ON-App) oder über das Online-Serviceportal Mein E.ON erfolgt.Bei einem Onlinevertrag erfolgt die vertragsbezogene Kommunikation durch E.ON elektronisch über das Online-Serviceportal „Mein E.ON“. Mit Abschluss des Onlinevertrages erklärt sich der Kunde damit einverstanden, dass E.ON dem Kunden rechtserhebliche Mitteilungen und Dokumente, etwa zur Begründung, Durchführung, Änderung oder Beendigung des Vertrages, ausschließlich in „Mein E.ON“ zur Verfügung stellt. E.ON behält sich das Recht vor, Preisänderungsmitteilungen, und sofern gesetzliche Bestimmungen oder sonstige Umstände es erforderlich machen, einzelne Mitteilungen und Dokumente weiterhin per Briefpost zu versenden.E.ON informiert den Kunden durch eine E-Mail an die vom Kunden im Rahmen der Registrierung angegebene E-Mail-Adresse, oder über einen anderen vom Kunden gewählten separaten Kommunikationskanal, wenn neue Post im Serviceportal „Mein E.ON“ bereit liegt.Der Kunde ist verpflichtet, die hinterlegte E-Mail-Adresse stets aktuell und funktionsfähig zu halten, so dass gewährleistet ist, dass diesem von E.ON abgegebene Erklärungen und Dokumente zugehen können. Die Änderung der E-Mail-Adresse ist E.ON unverzüglich mitzuteilen. Stehen dem Kunden die technischen Möglichkeiten zum Abrufen der Mitteilungen nicht mehr zur Verfügung, ist der Kunde verpflichtet, E.ON dies unverzüglich mitzuteilen. E.ON behält sich vor, für den Fall, dass dem Kunden eine Mitteilung nicht zugegangen sein sollte bzw. nicht zustellbar ist, für die erneute Übermittlung eine andere Form der Übersendung (z. B. per Post) zu wählen. Der Kunde kann ebenfalls über das Serviceportal mit E.ON kommunizieren. Zusätzlich stehen dem Kunden die übrigen Kontaktmöglichkeiten (z. B. postalisch, E-Mail, Onlinekontaktformular usw.) zur Verfügung.Aufgrund der Online-Kommunikation ist die Registrierung für das Online-Serviceportal „Mein E.ON“ für den Kunden verpflichtend. Hierzu ist der Einsatz gängiger Browsers erforderlich. Um sich bei „Mein E.ON“ zu registrieren erhält der Kunde eine E-Mail mit einem Aktivierungslink.", False),
    ("para", "3.5.2 Kommunikation bei nicht online geschlossenen VerträgenHat der Kunde keinen Onlinevertrag im Sinne der vorstehenden Ziffer (Ziffer mit der Überschrift „Onlinevertrag“) geschlossen, ist die Registrierung und Nutzung des Online-Serviceportals „Mein E.ON“ sowie die unter der vorstehenden Ziffer (Ziffer mit Überschrift Onlinevertrag) beschriebene Online-Kommunikation optional. Der Kunde kann sich jederzeit im Serviceportal „Mein E.ON“ registrieren.Entscheidet sich der Kunde für die Registrierung und die unter vorstehender Ziffer beschriebene Online-Kommunikation, werden dem Kunden vertragsbezogene Informationen und Mitteilungen zum Vertrag über das persönliche passwortgeschützte Online-Serviceportal „Mein E.ON“ zugestellt und der Kunde wird über den Posteingang über einen separaten Kontaktkanal informiert. Im Hinblick auf die Rechte und Pflichten im Zusammenhang mit der Registrierung und Nutzung von „Mein E.ON“ sowie der Online-Kommunikation gelten die Regelungen zu „Serviceportal Mein E.ON“ und „Onlinevertrag“ dieser Preis- und Lieferbedingungen mit der Ausnahme, dass die Registrierung in „Mein E.ON“ für den Kunden optional ist.", False),
    ("gap", 10, None),
    ("head", "3.6 Kommunikation per SMS", True),
    ("para", "Der Kunde kann im Serviceportal „Mein E.ON“ den SMS-Service aktivieren, um sich Informationen zu seinem Vertrag (z. B. Zahlungserinnerungen) per SMS zusenden zu lassen. Wird der SMS-Service vom Kunden aktiviert, ist der Kunde verpflichtet, E.ON die Änderung der Mobilfunknummer unverzüglich mitzuteilen, damit keine Vertragsinformationen an Dritte gelangen. Die Kommunikation per SMS kann jederzeit deaktiviert werden.", False),
    ("gap", 10, None),
    ("head", "3.7 Sonderkündigungsrecht bei fehlender Mein E.ON Registrierung für Onlineverträge", True),
    ("para", "E.ON ist berechtigt den Vertrag mit einer Frist von 4 Wochen außerordentlich zu kündigen, wenn ein Kunde mit Onlinevertrag im Sinne dieser Preis- und Lieferbedingungen (Ziffer mit Überschrift Onlinevertrag) die Registrierung für das Online-Serviceportal „Mein E.ON“ innerhalb von 2 Monaten nach Zugang des Vertragsbestätigungsschreibens nicht vornimmt. Die Kündigung durch E.ON setzt voraus, dass der Kunde vor Erklärung der Kündigung zweimal aufgefordert wurde, sich innerhalb einer angemessenen Frist im Online-Serviceportal „Mein E.ON“ zu registrieren. Die letzte Registrierungsaufforderung erfolgt unter Kündigungsandrohung. Die Registrierungsaufforderung und die Kündigung bedürfen der Textform.", False),
    ("gap", 10, None),
    ("head", "3.8 Laufzeit und Kündigung", True),
    ("para", "3.8.1 Die Erstvertragslaufzeit des Vertrages beträgt 24 Monate gerechnet ab Zugang der Vertragsbestätigung. Der Vertrag verlängert sich danach automatisch auf unbestimmte Zeit, sofern er nicht zum Ende der Erstvertragslaufzeit unter Einhaltung der ordentlichen Kündigungsfrist gekündigt wird. Verlängert sich der Vertrag auf unbestimmte Zeit, so kann dieser jederzeit unter Einhaltung der ordentlichen Kündigungsfrist gekündigt werden. Die ordentliche Kündigungsfrist beträgt 4 Wochen.", False),
    ("para", "3.8.2 Darüber hinaus enthält dieser Vertrag Sonderkündigungsrechte im Falle einer Preisänderung, einer Änderung der Vertragsbedingungen, eines Umzugs, gegebenenfalls im Falle einer fehlenden Registrierung für das Online-Serviceportal sowie im Falle des Nichtvorliegens der Voraussetzungen für die Stromlieferung. Einzelheiten finden Sie jeweils in den entsprechenden Regelungen dieses Vertrages.", False),
    ("para", "3.8.3 Eine Kündigung aus den vorgenannten Gründen bedarf der Textform (z. B. Brief, E-Mail). Wir bestätigen Kündigungen durch Sie innerhalb einer Woche nach Zugang unter Angabe des Vertragsendes in Textform.", False),
    ("para", "3.8.4 Das Recht zur Kündigung aus wichtigem Grund nach § 314 BGB bleibt unberührt.", False),
]

def wrap(draw, text, fnt, width):
    words, lines, line = text.split(), [], ""
    for word in words:
        trial = (line + " " + word).strip()
        if draw.textlength(trial, font=fnt) <= width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines

def build():
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    body, head = font(BODY), font(HEAD, True)
    left = int(52 * SCALE)
    right = int(52 * SCALE)
    text_w = W - left - right
    y = int(38 * SCALE)
    step = int(BODY * 1.55)
    for kind, value, bold in DOC:
        if kind == "gap":
            y += int(value * SCALE)
            continue
        if kind == "right":
            d.text((W - right, y), value, font=body, fill="black", anchor="ra")
            y += step
            continue
        fnt = head if kind == "head" else body
        for line in wrap(d, value, fnt, text_w):
            d.text((left, y), line, font=fnt, fill="black")
            y += step
    return img, y

if __name__ == "__main__":
    import os
    where = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(where, exist_ok=True)
    img, used = build()
    img.save(os.path.join(where, "german-contract.png"))
    print("page %dx%d, text ends at y=%d (%.0f%% of the page)"
          % (img.width, img.height, used, 100.0 * used / img.height))
