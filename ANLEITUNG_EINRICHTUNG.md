# RetailMind AI einrichten

Du musst nichts installieren. Alles läuft im Browser. Du legst sechs Konten an und trägst Schlüssel ein. Plane dafür etwa zwei Stunden ein und geh in dieser Reihenfolge vor. Nach jedem Schritt prüfst du in der App unter **System check**, ob der Punkt grün ist.

| Konto | Wofür | Kosten |
|---|---|---|
| GitHub | Ablage des Codes, Zeitplaner | kostenlos |
| Streamlit Community Cloud | Öffentlicher Link zur App | kostenlos |
| Anthropic Console | Sprachmodell | Guthaben aufladen, 5 USD reichen für den Prototyp |
| Supabase | Speicher für Automatisierungen und Versandprotokoll | kostenlos |
| Gmail (neues Projektkonto) | Mailversand | kostenlos |
| Telegram (BotFather) | Sofortkanal per Messenger | kostenlos |

Lege dir eine Notiz an, in der du alle Schlüssel sammelst. Schlüssel gehören nie in eine Datei auf GitHub.

## 1. Code auf GitHub ablegen

1. Konto auf github.com anlegen.
2. Oben rechts auf das Plus, **New repository**. Name `retailmind-ai`, Sichtbarkeit **Public**, anlegen. Public ist wichtig, weil der Zeitplaner dort unbegrenzt kostenlos läuft. Im Code stehen keine Schlüssel.
3. Die ZIP Datei entpacken. Auf dem Mac im Finder **Cmd + Shift + Punkt** drücken, damit die Ordner `.github` und `.streamlit` sichtbar werden.
4. Im leeren Repository auf **uploading an existing file** klicken, den gesamten Inhalt des entpackten Ordners hineinziehen (Inhalt, nicht den Ordner selbst) und unten **Commit changes**.
5. Kontrolle: Im Repository muss die Datei `.github/workflows/scheduler.yml` zu sehen sein. Fehlt sie, dann **Add file, Create new file**, als Namen genau `.github/workflows/scheduler.yml` eintippen und den Inhalt der Datei aus dem ZIP hineinkopieren.

## 2. App veröffentlichen

1. Auf share.streamlit.io mit dem GitHub Konto anmelden.
2. **Create app**, dann dein Repository wählen, Branch `main`, Main file `app.py`. Bei **App URL** einen Namen vergeben, zum Beispiel `retailmind-ai`.
3. **Deploy**. Nach ein paar Minuten läuft die App. Die Wissensbasis ist schon sichtbar, alles andere ist unter System check noch rot.
4. In der App unten rechts **Manage app**, dann die drei Punkte, **Settings, Secrets**. Dort den Inhalt von `secrets_template.toml` einfügen. Trage zuerst nur `APP_ACCESS_CODE` (frei wählbar) und `APP_URL` (dein Link) ein. Die anderen Zeilen füllst du in den nächsten Schritten. Zeilen mit Platzhaltern kannst du solange löschen.

## 3. Sprachmodell

1. Auf console.anthropic.com Konto anlegen, unter **Billing** 5 USD Guthaben laden.
2. Unter **API Keys** einen Schlüssel erzeugen und sofort kopieren.
3. In den Streamlit Secrets `ANTHROPIC_API_KEY` eintragen, speichern.
4. In der App: System check, **Test language model**. Erwartet wird "Model answered: READY".
5. Kommt eine Meldung, dass das Modell nicht gefunden wurde, trag bei `ANTHROPIC_MODEL` einen Modellnamen aus der Modellübersicht der Console ein.

Ab jetzt funktioniert **Ask the research**.

## 4. Speicher

1. Auf supabase.com Konto anlegen, **New project**, Region Frankfurt, Datenbankpasswort notieren.
2. Links **SQL Editor**, **New query**, den Inhalt von `supabase_setup.sql` einfügen, **Run**.
3. In den Projekteinstellungen unter **API** die **Project URL** kopieren und den geheimen Schlüssel (heißt je nach Oberfläche **secret key** oder **service_role**). Nicht den öffentlichen Schlüssel nehmen.
4. In die Streamlit Secrets als `SUPABASE_URL` und `SUPABASE_KEY` eintragen.
5. System check, **Test storage**. Erwartet: "Supabase reachable, both tables found."

## 5. Mail

1. Ein neues Gmail Konto für das Projekt anlegen. Nimm nicht dein privates Postfach.
2. Im Google Konto unter Sicherheit die **Bestätigung in zwei Schritten** einschalten.
3. Auf myaccount.google.com/apppasswords ein **App Passwort** erzeugen (16 Zeichen).
4. In die Secrets: `SMTP_USER` ist die Gmail Adresse, `SMTP_PASSWORD` das App Passwort. `SMTP_HOST` und `SMTP_PORT` bleiben wie in der Vorlage.
5. In der App links dein Profil speichern, dann System check, **Send test email**.

## 6. Telegram

1. Telegram öffnen (App oder web.telegram.org) und nach **@BotFather** suchen. Das ist der offizielle Bot von Telegram, erkennbar am blauen Haken.
2. `/newbot` schicken. Als Namen `RetailMind AI` eingeben, als Benutzernamen etwas Eindeutiges, das auf `bot` endet, zum Beispiel `retailmind_cbs_bot`.
3. BotFather antwortet mit einem **Token** (Zahlen, Doppelpunkt, Buchstaben). Das ist der Schlüssel des Bots.
4. In die Streamlit Secrets `TELEGRAM_BOT_TOKEN` eintragen und speichern.
5. In der App links das Profil speichern, dann **Open RetailMind in Telegram** klicken, in Telegram **Start** drücken und zurück in der App **Check connection** klicken.
6. System check, **Send test Telegram**.

Jede Person, die Telegram Briefings bekommen soll, verbindet sich einmal auf diesem Weg.

## 7. Zeitplaner

Der Zeitplaner läuft bei GitHub und braucht die Schlüssel ein zweites Mal.

1. Im Repository **Settings, Secrets and variables, Actions**.
2. Unter **Secrets** jeweils mit **New repository secret** anlegen, Namen exakt so: `ANTHROPIC_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`, `SMTP_USER`, `SMTP_PASSWORD`, `TELEGRAM_BOT_TOKEN`.
3. Unter **Variables** anlegen: `APP_URL`. Falls du in Schritt 3 das Modell geändert hast, auch `ANTHROPIC_MODEL`.
4. Oben im Repository auf **Actions**, Workflows erlauben, links **RetailMind scheduler**, **Run workflow**.
5. Den Lauf anklicken. Im Schritt `python scheduler.py` muss stehen: `Storage: supabase | due automations: 0`.

## 8. Gesamttest

1. In der App unter Automations die drei Vorlagen aus **Quick start** hinzufügen.
2. Bei jeder **Send now** drücken. Mail und Telegram müssen ankommen, der Eintrag erscheint im Delivery log.
3. Für den Test des Zeitplaners eine Automatisierung **Daily** auf die nächste volle Stunde legen und abwarten. Die Zustellung kommt bis etwa 30 Minuten nach der gewählten Zeit.

## Wissensbasis pflegen

Die Datei `knowledge_base.xlsx` ist euer Datenfundament. Auf dem Blatt "How to fill in" stehen die Regeln. Nach dem Bearbeiten die Datei im Repository über **Add file, Upload files** ersetzen. Die App lädt sich danach selbst neu.

Die 14 Starteinträge habe ich aus dem Gedächtnis angelegt, damit die App testbar ist. Sie sind in der App als "not yet verified" markiert. Jeder Eintrag samt DOI muss von euch am Original geprüft werden, bevor er in den Pitch geht.

## Grenzen, die ihr kennen und im Pitch offen benennen solltet

* **Kein eigenes Sprachmodell.** Ein bestehendes Modell antwortet ausschließlich auf Basis eurer geprüften Artikel und nennt die Quelle.
* **Fester Datensatz.** Die Automatisierungen gehen die Artikel der Reihe nach durch. Nach einem Durchlauf beginnen sie von vorn. Neue Inhalte gibt es nur, wenn ihr Artikel ergänzt.
* **Telegram statt WhatsApp.** Die WhatsApp Testumgebung von Twilio erlaubt über die Schnittstelle nur feste Vorlagen, keinen freien Text. Im echten Betrieb bräuchte WhatsApp von Meta genehmigte Vorlagen. Telegram liefert ohne diese Einschränkung. Ist Telegram nicht verbunden, kommt der Bericht per Mail.
* **LinkedIn wird nicht automatisch veröffentlicht.** Der Entwurf kommt zum gewählten Zeitpunkt, veröffentlicht wird mit einem Klick durch die Person selbst.
* **Zeitplaner mit Verzögerung.** GitHub startet zweimal pro Stunde und manchmal einige Minuten später.
* **Anmeldung ohne Passwort.** Wer den Zugangscode und eine Mailadresse kennt, sieht die Automatisierungen dieser Adresse. Für einen Prototyp in Ordnung, für den echten Einsatz nicht.
* Die kostenlose App schläft nach längerer Inaktivität ein. Vor der Demo einmal öffnen.
