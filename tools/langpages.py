"""One document, written out in ten languages, as a test page each.

Every page has the same shape — a heading, two columns of prose, a table
with a row of headers and three rows of values, a numbered list, and a
footer carrying an address and a reference — so the ten results can be put
beside each other and compared. Where a page reads badly, the difference
is the language, because nothing else differs.

The boxes are recorded as they are drawn, so the reading and the layout
can be scored separately: with the true lines in hand a fault in the
grouping is a fault in the grouping, not the recogniser having a bad day.

    python tools/langpages.py <folder>
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PIL import Image, ImageDraw                              # noqa: E402

from app import overlay                                       # noqa: E402

# The working languages: the ones business documents arrive in here.
#
# Hindi, Arabic and Russian were in this list and came out of it. The
# machinery is not language-specific and the pages for them are kept in
# `DOC` below, so any of the three goes back in by adding its code — but
# a test that is never looked at is a test that quietly rots, and these
# nine are the ones somebody reads the result of.
LANGUAGES = ["en", "de", "fr", "es", "it", "pt", "zh-CN", "ja", "ko"]

DOC = {
 "en": {
  "title": "Notice on the annual maintenance of the reporting system",
  "sub": "Document LH-2026-037 | Issued 18 September 2026",
  "left": ["The maintenance will be carried out by the technical department "
           "on 2 September 2026. Some services will be unavailable during "
           "the night and the early morning.",
           "Please make your arrangements in advance and avoid submitting "
           "important documents in that window. The help desk stays open "
           "throughout."],
  "right": ["After the work is finished every employee will have to sign in "
            "again, because the single sign-on service is being replaced at "
            "the same time.",
            "If your password is refused, wait two hours before calling: the "
            "directory takes that long to settle everywhere."],
  "head": ["System", "Window", "Owner"],
  "rows": [["Financial ledger", "22:00 - 04:00", "A. Weber"],
           ["Mail gateway", "01:00 - 03:30", "L. Jing"],
           ["Remote access", "03:00 - 05:00", "W. Jianguo"]],
  "list": ["Confirm the daily report before 18:00.",
           "Do not change the network settings during the window.",
           "Report the state of your department by 09:00 the next day."],
  "foot": "Technical department | it-ops@example.internal | ref 8137",
 },
 "de": {
  "title": "Mitteilung zur jaehrlichen Wartung des Berichtssystems",
  "sub": "Dokument LH-2026-037 | Ausgegeben am 18. September 2026",
  "left": ["Die Wartung wird am 2. September 2026 von der technischen "
           "Abteilung durchgefuehrt. Einige Dienste stehen in der Nacht und "
           "am fruehen Morgen nicht zur Verfuegung.",
           "Bitte treffen Sie Ihre Vorkehrungen rechtzeitig und reichen Sie "
           "in diesem Zeitraum keine wichtigen Unterlagen ein. Der Helpdesk "
           "bleibt durchgehend erreichbar."],
  "right": ["Nach Abschluss der Arbeiten muessen sich alle Mitarbeitenden "
            "erneut anmelden, da der Anmeldedienst gleichzeitig ersetzt "
            "wird.",
            "Wird Ihr Kennwort abgelehnt, warten Sie zwei Stunden vor einem "
            "Anruf: so lange braucht das Verzeichnis ueberall."],
  "head": ["System", "Zeitfenster", "Zustaendig"],
  "rows": [["Finanzbuchhaltung", "22:00 - 04:00", "A. Weber"],
           ["Mail-Gateway", "01:00 - 03:30", "L. Jing"],
           ["Fernzugriff", "03:00 - 05:00", "W. Jianguo"]],
  "list": ["Bestaetigen Sie den Tagesbericht vor 18:00 Uhr.",
           "Aendern Sie die Netzwerkeinstellungen im Zeitfenster nicht.",
           "Melden Sie den Stand Ihrer Abteilung bis 09:00 Uhr am Folgetag."],
  "foot": "Technische Abteilung | it-ops@example.internal | Az. 8137",
 },
 "fr": {
  "title": "Avis concernant la maintenance annuelle du systeme de rapports",
  "sub": "Document LH-2026-037 | Publie le 18 septembre 2026",
  "left": ["La maintenance sera effectuee par le service technique le 2 "
           "septembre 2026. Certains services seront indisponibles pendant "
           "la nuit et au petit matin.",
           "Veuillez prendre vos dispositions a l'avance et eviter de "
           "deposer des documents importants dans ce creneau. L'assistance "
           "reste ouverte."],
  "right": ["Une fois les travaux termines, chaque employe devra se "
            "reconnecter, car le service d'authentification unique est "
            "remplace en meme temps.",
            "Si votre mot de passe est refuse, attendez deux heures avant "
            "d'appeler : l'annuaire met ce temps a se propager."],
  "head": ["Systeme", "Creneau", "Responsable"],
  "rows": [["Grand livre", "22:00 - 04:00", "A. Weber"],
           ["Passerelle de messagerie", "01:00 - 03:30", "L. Jing"],
           ["Acces distant", "03:00 - 05:00", "W. Jianguo"]],
  "list": ["Confirmez le rapport quotidien avant 18:00.",
           "Ne modifiez pas les reglages reseau pendant le creneau.",
           "Signalez l'etat de votre service avant 09:00 le lendemain."],
  "foot": "Service technique | it-ops@example.internal | ref 8137",
 },
 "es": {
  "title": "Aviso sobre el mantenimiento anual del sistema de informes",
  "sub": "Documento LH-2026-037 | Emitido el 18 de septiembre de 2026",
  "left": ["El mantenimiento lo realizara el departamento tecnico el 2 de "
           "septiembre de 2026. Algunos servicios no estaran disponibles "
           "durante la noche y la madrugada.",
           "Tome sus precauciones con antelacion y evite presentar "
           "documentos importantes en esa franja. El servicio de ayuda "
           "sigue abierto."],
  "right": ["Cuando terminen los trabajos, todos los empleados tendran que "
            "volver a iniciar sesion, porque el servicio de acceso unico se "
            "sustituye al mismo tiempo.",
            "Si se rechaza su contrasena, espere dos horas antes de llamar: "
            "el directorio tarda ese tiempo en propagarse."],
  "head": ["Sistema", "Franja", "Responsable"],
  "rows": [["Libro mayor", "22:00 - 04:00", "A. Weber"],
           ["Pasarela de correo", "01:00 - 03:30", "L. Jing"],
           ["Acceso remoto", "03:00 - 05:00", "W. Jianguo"]],
  "list": ["Confirme el informe diario antes de las 18:00.",
           "No cambie la configuracion de red durante la franja.",
           "Comunique el estado de su departamento antes de las 09:00."],
  "foot": "Departamento tecnico | it-ops@example.internal | ref 8137",
 },
 "it": {
  "title": "Avviso sulla manutenzione annuale del sistema di rendicontazione",
  "sub": "Documento LH-2026-037 | Emesso il 18 settembre 2026",
  "left": ["La manutenzione sara eseguita dal reparto tecnico il 2 settembre "
           "2026. Alcuni servizi non saranno disponibili durante la notte e "
           "al primo mattino.",
           "Si prega di organizzarsi in anticipo e di evitare di presentare "
           "documenti importanti in quella fascia. L'assistenza resta "
           "aperta."],
  "right": ["Al termine dei lavori tutti i dipendenti dovranno accedere di "
            "nuovo, perche il servizio di accesso unico viene sostituito "
            "nello stesso momento.",
            "Se la password viene rifiutata, attenda due ore prima di "
            "chiamare: la rubrica impiega questo tempo a propagarsi."],
  "head": ["Sistema", "Fascia", "Responsabile"],
  "rows": [["Contabilita generale", "22:00 - 04:00", "A. Weber"],
           ["Gateway di posta", "01:00 - 03:30", "L. Jing"],
           ["Accesso remoto", "03:00 - 05:00", "W. Jianguo"]],
  "list": ["Confermare il rapporto giornaliero entro le 18:00.",
           "Non modificare le impostazioni di rete durante la fascia.",
           "Segnalare lo stato del proprio reparto entro le 09:00."],
  "foot": "Reparto tecnico | it-ops@example.internal | rif 8137",
 },
 "pt": {
  "title": "Aviso sobre a manutencao anual do sistema de relatorios",
  "sub": "Documento LH-2026-037 | Emitido em 18 de setembro de 2026",
  "left": ["A manutencao sera realizada pelo departamento tecnico em 2 de "
           "setembro de 2026. Alguns servicos ficarao indisponiveis durante "
           "a noite e a madrugada.",
           "Tome as suas providencias com antecedencia e evite enviar "
           "documentos importantes nesse periodo. O servico de apoio "
           "continua aberto."],
  "right": ["Depois de concluidos os trabalhos, todos os funcionarios terao "
            "de iniciar sessao novamente, porque o servico de acesso unico "
            "esta a ser substituido ao mesmo tempo.",
            "Se a sua palavra-passe for recusada, aguarde duas horas antes "
            "de telefonar: o diretorio demora esse tempo a propagar-se."],
  "head": ["Sistema", "Periodo", "Responsavel"],
  "rows": [["Livro razao", "22:00 - 04:00", "A. Weber"],
           ["Gateway de correio", "01:00 - 03:30", "L. Jing"],
           ["Acesso remoto", "03:00 - 05:00", "W. Jianguo"]],
  "list": ["Confirme o relatorio diario antes das 18:00.",
           "Nao altere as definicoes de rede durante o periodo.",
           "Comunique o estado do seu departamento ate as 09:00."],
  "foot": "Departamento tecnico | it-ops@example.internal | ref 8137",
 },
 "ru": {
  "title": "Уведомление о ежегодном обслуживании системы отчетности",
  "sub": "Документ LH-2026-037 | Выпущен 18 сентября 2026 года",
  "left": ["Обслуживание проведет технический отдел 2 сентября 2026 года. "
           "Некоторые службы будут недоступны ночью и ранним утром.",
           "Просим подготовиться заранее и не подавать важные документы в "
           "этот период. Служба поддержки работает без перерыва."],
  "right": ["После завершения работ всем сотрудникам придется войти в "
            "систему заново, поскольку служба единого входа заменяется "
            "одновременно.",
            "Если пароль отклонен, подождите два часа перед звонком: "
            "каталогу нужно столько времени на обновление."],
  "head": ["Система", "Окно", "Ответственный"],
  "rows": [["Главная книга", "22:00 - 04:00", "А. Вебер"],
           ["Почтовый шлюз", "01:00 - 03:30", "Л. Цзин"],
           ["Удаленный доступ", "03:00 - 05:00", "В. Цзяньго"]],
  "list": ["Подтвердите ежедневный отчет до 18:00.",
           "Не меняйте сетевые настройки во время работ.",
           "Сообщите о состоянии отдела до 09:00 следующего дня."],
  "foot": "Технический отдел | it-ops@example.internal | исх. 8137",
 },
 "hi": {
  "title": "रिपोर्टिंग प्रणाली के वार्षिक रखरखाव की सूचना",
  "sub": "दस्तावेज LH-2026-037 | 18 सितंबर 2026 को जारी",
  "left": ["रखरखाव तकनीकी विभाग द्वारा 2 सितंबर 2026 को किया जाएगा। रात और "
           "तड़के कुछ सेवाएं उपलब्ध नहीं रहेंगी।",
           "कृपया अपनी व्यवस्था पहले से कर लें और इस अवधि में महत्वपूर्ण "
           "दस्तावेज न भेजें। सहायता केंद्र पूरे समय खुला रहेगा।"],
  "right": ["काम पूरा होने के बाद हर कर्मचारी को दोबारा साइन इन करना होगा, "
            "क्योंकि एकल साइन-ऑन सेवा उसी समय बदली जा रही है।",
            "यदि आपका पासवर्ड अस्वीकार हो, तो फोन करने से पहले दो घंटे "
            "प्रतीक्षा करें: निर्देशिका को इतना समय लगता है।"],
  "head": ["प्रणाली", "अवधि", "प्रभारी"],
  "rows": [["वित्तीय बही", "22:00 - 04:00", "ए. वेबर"],
           ["मेल गेटवे", "01:00 - 03:30", "एल. जिंग"],
           ["दूरस्थ पहुंच", "03:00 - 05:00", "डब्ल्यू. जियांगुओ"]],
  "list": ["दैनिक रिपोर्ट 18:00 से पहले पुष्ट करें।",
           "इस अवधि में नेटवर्क सेटिंग न बदलें।",
           "अगले दिन 09:00 तक अपने विभाग की स्थिति बताएं।"],
  "foot": "तकनीकी विभाग | it-ops@example.internal | संदर्भ 8137",
 },
 "zh-CN": {
  "title": "关于报告系统年度维护的通知",
  "sub": "文件 LH-2026-037 | 2026年9月18日发布",
  "left": ["维护将由技术部门于2026年9月2日进行。夜间和清晨部分服务将无法使用。",
           "请提前做好安排，避免在该时段提交重要文件。服务台全程开放。"],
  "right": ["工作完成后，所有员工需要重新登录，因为单点登录服务同时更换。",
            "如果密码被拒绝，请等待两小时后再致电：目录需要这段时间才能同步。"],
  "head": ["系统", "时段", "负责人"],
  "rows": [["财务总账", "22:00 - 04:00", "韦伯"],
           ["邮件网关", "01:00 - 03:30", "李静"],
           ["远程访问", "03:00 - 05:00", "王建国"]],
  "list": ["请在18:00前确认日报。", "维护期间请勿更改网络设置。",
           "次日09:00前报告本部门状态。"],
  "foot": "技术部 | it-ops@example.internal | 编号 8137",
 },
 "ja": {
  "title": "報告システムの年次保守に関するお知らせ",
  "sub": "文書 LH-2026-037 | 2026年9月18日発行",
  "left": ["保守は技術部が2026年9月2日に実施します。夜間および早朝は一部の"
           "サービスがご利用いただけません。",
           "あらかじめご準備のうえ、この時間帯に重要書類を提出しないよう"
           "お願いします。窓口は終日開いています。"],
  "right": ["作業終了後、全社員が再度サインインする必要があります。"
            "シングルサインオンも同時に入れ替わるためです。",
            "パスワードが拒否された場合は、二時間待ってからご連絡ください。"
            "反映にそれだけの時間がかかります。"],
  "head": ["システム", "時間帯", "担当"],
  "rows": [["財務元帳", "22:00 - 04:00", "ウェーバー"],
           ["メールゲートウェイ", "01:00 - 03:30", "リ・ジン"],
           ["リモート接続", "03:00 - 05:00", "ワン・ジェングオ"]],
  "list": ["日報は18:00までに確認してください。",
           "この時間帯にネットワーク設定を変更しないでください。",
           "翌日09:00までに部署の状況を報告してください。"],
  "foot": "技術部 | it-ops@example.internal | 整理番号 8137",
 },
 "ko": {
  "title": "보고 시스템 연간 유지보수 안내",
  "sub": "문서 LH-2026-037 | 2026년 9월 18일 발행",
  "left": ["유지보수는 기술부가 2026년 9월 2일에 수행합니다. 야간과 이른 "
           "아침에는 일부 서비스를 이용할 수 없습니다.",
           "미리 준비하시고 해당 시간대에는 중요한 문서를 제출하지 "
           "마십시오. 지원 창구는 계속 열려 있습니다."],
  "right": ["작업이 끝나면 모든 직원이 다시 로그인해야 합니다. 통합 로그인 "
            "서비스도 같은 시간에 교체되기 때문입니다.",
            "비밀번호가 거부되면 두 시간 기다린 뒤에 전화하십시오. "
            "디렉터리 반영에 그만큼 걸립니다."],
  "head": ["시스템", "시간대", "담당"],
  "rows": [["재무 원장", "22:00 - 04:00", "베버"],
           ["메일 게이트웨이", "01:00 - 03:30", "리징"],
           ["원격 접속", "03:00 - 05:00", "왕젠궈"]],
  "list": ["일일 보고는 18:00 전에 확인하십시오.",
           "해당 시간대에 네트워크 설정을 변경하지 마십시오.",
           "다음 날 09:00까지 부서 상태를 보고하십시오."],
  "foot": "기술부 | it-ops@example.internal | 참조 8137",
 },
 "ar": {
  "title": "إشعار بشأن الصيانة السنوية لنظام التقارير",
  "sub": "الوثيقة LH-2026-037 | صدرت في 18 سبتمبر 2026",
  "left": ["ستنفذ الدائرة الفنية الصيانة في 2 سبتمبر 2026. لن تتوفر بعض "
           "الخدمات خلال الليل وفي الصباح الباكر.",
           "يرجى اتخاذ ترتيباتكم مسبقا وتجنب تقديم مستندات مهمة في تلك "
           "الفترة. يبقى مكتب المساعدة مفتوحا."],
  "right": ["بعد انتهاء العمل سيتعين على كل موظف تسجيل الدخول من جديد، لأن "
            "خدمة الدخول الموحد تستبدل في الوقت نفسه.",
            "إذا رفضت كلمة المرور فانتظر ساعتين قبل الاتصال: يحتاج الدليل "
            "هذا الوقت للتحديث."],
  "head": ["النظام", "الفترة", "المسؤول"],
  "rows": [["دفتر الأستاذ", "22:00 - 04:00", "أ. ويبر"],
           ["بوابة البريد", "01:00 - 03:30", "ل. جينغ"],
           ["الوصول عن بعد", "03:00 - 05:00", "و. جيانغو"]],
  "list": ["أكد التقرير اليومي قبل الساعة 18:00.",
           "لا تغير إعدادات الشبكة خلال الفترة.",
           "أبلغ عن حالة قسمك قبل الساعة 09:00."],
  "foot": "الدائرة الفنية | it-ops@example.internal | مرجع 8137",
 },
}

WIDTH = 900
MARGIN = 56
GUTTER = 36
BODY = 15
TITLE = 26
SUB = 12


def draw_block(draw, text, font, x, y, width, colour, lines, kind,
               leading=None):
    """Write one paragraph, recording the box of every line drawn.

    Every line also carries the number of the paragraph it came from. That
    is the ground truth the grouping is scored against: the app has to
    gather these lines back into the paragraphs they were written as, and
    without this the only way to check is to read the page and judge.
    """
    pid = draw_block.pid = getattr(draw_block, "pid", 0) + 1
    lead = leading or int(font.size * 1.45)
    rows = overlay._wrap(draw, text, font, width)
    for row in rows:
        draw.text((x, y), row, font=font, fill=colour)
        box = draw.textbbox((x, y), row, font=font)
        lines.append({"box": (box[0], box[1], max(1, box[2] - box[0]),
                              max(1, box[3] - box[1])),
                      "text": row, "kind": kind, "pid": pid})
        y += lead
    return y


def build(code):
    draw_block.pid = 0
    doc = DOC[code]
    kind = overlay._font_family_for(code)
    body = overlay.load_font(kind, BODY)
    title = overlay.load_font(kind, TITLE)
    sub = overlay.load_font(kind, SUB)
    page = Image.new("RGB", (WIDTH, 1400), "white")
    draw = ImageDraw.Draw(page)
    lines = []
    column = (WIDTH - 2 * MARGIN - GUTTER) // 2

    y = MARGIN
    y = draw_block(draw, doc["title"], title, MARGIN, y,
                   WIDTH - 2 * MARGIN, (16, 16, 16), lines, "title",
                   int(TITLE * 1.35))
    y += 6
    y = draw_block(draw, doc["sub"], sub, MARGIN, y, WIDTH - 2 * MARGIN,
                   (90, 90, 90), lines, "sub", int(SUB * 1.6))
    y += 10
    draw.line([MARGIN, y, WIDTH - MARGIN, y], fill=(180, 180, 180))
    y += 18

    top = y
    left_y = top
    for para in doc["left"]:
        left_y = draw_block(draw, para, body, MARGIN, left_y, column,
                            (24, 24, 24), lines, "prose") + 10
    right_x = MARGIN + column + GUTTER
    right_y = top
    for para in doc["right"]:
        right_y = draw_block(draw, para, body, right_x, right_y, column,
                             (24, 24, 24), lines, "prose") + 10

    y = max(left_y, right_y) + 22
    cols = [MARGIN, MARGIN + 320, MARGIN + 560]
    for text, cx in zip(doc["head"], cols):
        draw_block(draw, text, body, cx, y, 260, (16, 16, 16), lines, "head")
    y += int(BODY * 1.9)
    draw.line([MARGIN, y - 8, WIDTH - MARGIN, y - 8], fill=(200, 200, 200))
    for row in doc["rows"]:
        for text, cx in zip(row, cols):
            draw_block(draw, text, body, cx, y, 260, (24, 24, 24), lines,
                       "cell")
        y += int(BODY * 2.1)

    y += 16
    for index, item in enumerate(doc["list"], 1):
        y = draw_block(draw, "%d. %s" % (index, item), body, MARGIN, y,
                       WIDTH - 2 * MARGIN, (24, 24, 24), lines, "item") + 6

    y += 20
    draw.line([MARGIN, y, WIDTH - MARGIN, y], fill=(180, 180, 180))
    y += 12
    y = draw_block(draw, doc["foot"], sub, MARGIN, y, WIDTH - 2 * MARGIN,
                   (110, 110, 110), lines, "foot", int(SUB * 1.6))

    return page.crop((0, 0, WIDTH, min(1400, y + MARGIN))), lines


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "langpages")
    os.makedirs(out, exist_ok=True)
    for code in LANGUAGES:
        page, lines = build(code)
        name = code.replace("-", "")
        page.save(os.path.join(out, "%s.png" % name))
        with open(os.path.join(out, "%s.json" % name), "w",
                  encoding="utf-8") as fh:
            json.dump({"lang": code, "size": page.size, "lines": lines}, fh,
                      ensure_ascii=False)
        print("%-6s %d lines  %dx%d" % (code, len(lines), *page.size))


if __name__ == "__main__":
    main()
