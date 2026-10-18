**🇬🇧 [English version / Englische Anleitung](README.md)**

# Sovol-SV08-Mainline
FÜR STABILITÄT DAS HAUPT-REPO NUTZEN >>> [Rappetor/Sovol-SV08-Mainline](https://github.com/Rappetor/Sovol-SV08-Mainline)

Den Sovol SV08 auf Mainline-Klipper bringen

Diese Anleitung beschreibt, wie du Mainline-Klipper (also das normale Klipper, per KIAUH) mit dem BTT-CB1-Image auf deinem Sovol SV08 installierst.<br>

Das System kann wahlweise vom eMMC oder von einer SD-Karte laufen.<br>

> [!NOTE]
> **Zu diesem Fork:** Nach der Grundinstallation richtet der Installer in [`sv08-loadcell/`](sv08-loadcell/README.md) die komplette Druckerkonfiguration in einem Rutsch ein (**Schritt 8**). Er ersetzt den Konfigurationsschritt der Original-Anleitung, in dem alles von Hand kopiert wird, und bringt zusätzlich Z-Homing auf der Sovol-Wägezelle, einen automatischen Z-Offset vor jedem Druck, automatische Düsenreinigung und einen Kalibrierungs-Assistenten mit. Gedacht für SV08 mit **Original-Hardware** (induktive Probe + Wägezelle).

**Kurzfassung**: _Klipper-Config sichern, eMMC aus dem Drucker ausbauen, CB1-Image auf den eMMC schreiben, BoardEnv.txt und system.cfg anpassen, eMMC wieder einbauen, KIAUH installieren und damit Klipper, Moonraker, Mainsail und Crowsnest, Original-Firmware sichern, Katapult und Klipper auf Druckkopf- und Mainboard-MCU flashen, sv08-loadcell-Installer und Kalibrierungs-Assistent laufen lassen. FERTIG!_

<br>

# ZUERST LESEN!

<h3>Video-Anleitungen können veraltet sein. Maßgeblich ist immer dieses Repo mit dem aktuellen Stand.</h3>
<h3>WIR ÜBERNEHMEN KEINE HAFTUNG FÜR SCHÄDEN AN DEINEM DRUCKER.</h3>

<p>Davon abgesehen wurden alle Schritte von mehreren Leuten aus der Community gründlich getestet. Halte dich genau und sorgfältig an die Schritte, dann hast du am Ende einen gut funktionierenden Drucker. Wenn du irgendwo hängst oder Fragen hast, eröffne ein Issue oder frag auf dem (offiziellen oder inoffiziellen) Sovol-Discord nach.</p>

<br><br>

Diese Anleitung hebt wichtige Infos farbig hervor.

> [!CAUTION]
> Text in einem roten Kasten MUSST du lesen.

> [!IMPORTANT]
> Text in einem lila Kasten ist eine wichtige Information.

> [!NOTE]
> Text in einem blauen Kasten ist meist ein hilfreicher Tipp oder ein nützlicher Hinweis.

So, jetzt kann es losgehen.

## IN ARBEIT

> [!NOTE]
> Diese Anleitung wird noch weiterentwickelt, an einigen Stellen gibt es noch zu tun. Du bist das Versuchskaninchen ;) <br> Etwas funktioniert nicht (richtig)? Bitte melde es und hilf mit!

# INHALT

- [Voraussetzungen](#voraussetzungen)
- [SCHRITT 1 - eMMC aus dem Drucker ausbauen](#schritt-1---emmc-aus-dem-drucker-ausbauen)
- [SCHRITT 2 - Speichermedium beschreiben](#schritt-2---speichermedium-beschreiben)
  - [METHODE 1: Image direkt auf den eMMC schreiben](#methode-1-image-direkt-auf-den-emmc-schreiben)
  - [METHODE 2: Image auf SD-Karte -> eMMC](#methode-2-image-auf-sd-karte---emmc)
  - [METHODE 4: Image per USB-C-Kabel direkt auf den eMMC schreiben](#methode-4-image-per-usb-c-kabel-direkt-auf-den-emmc-schreiben)
- [SCHRITT 3 - BoardEnv.txt anpassen & WLAN einrichten](#schritt-3---boardenvtxt-anpassen--wlan-einrichten)
- [SCHRITT 4 - Mainline-Klipper installieren](#schritt-4---mainline-klipper-installieren)
- [SCHRITT 5 - Original-Firmware sichern](#schritt-5---original-firmware-sichern)
- [SCHRITT 6 - Katapult-Bootloader flashen](#schritt-6---katapult-bootloader-flashen)
- [SCHRITT 7 - Klipper-Firmware auf die MCUs flashen](#schritt-7---klipper-firmware-auf-die-mcus-flashen)
- [SCHRITT 8 - Druckerkonfiguration installieren und kalibrieren](#schritt-8---druckerkonfiguration-installieren-und-kalibrieren)
- [Dank & Mitmachen](#dank--mitmachen)
- [Haftungsausschluss](#haftungsausschluss)

# VORAUSSETZUNGEN

- Erstelle zuerst ein **Backup** aller Config-Dateien deines Original-SV08. Das geht in der Web-Oberfläche (Mainsail) -> Maschine -> alle Dateien/Ordner auswählen -> Herunterladen.
  - Optional kannst du dich auch per SSH oder SFTP verbinden (Port 22, Benutzer/Passwort: sovol/sovol) und zusätzlich die .sh-Skripte im Ordner /home/sovol/ sichern.
  - Zum Beispiel mit [PuTTY](https://www.putty.org/) für SSH und [WinSCP](https://winscp.net/) für SFTP (_SSH File Transfer Protocol_).
- Heb die gesicherte printer.cfg auf: Sie enthält die Seriennummern deiner MCUs (`/dev/serial/by-id/usb-Klipper*stm32f103xe*`), das hilft in **Schritt 7**.
- Du brauchst entweder einen USB-Adapter '**Makerbase MKS EMMC-ADAPTER V2 USB 3.0**' oder einen '**Makerbase MKS MICROSD TO EMMC ADAPTER**', um den eMMC lesen und beschreiben zu können. <sub>*(Es geht auch ohne eMMC-Adapter: Entweder schreibst du das Image auf eine SD-Karte und von dort auf den eMMC, siehe 'Methode 2', oder du verbindest das Mainboard per USB-C mit deinem Computer, siehe 'Methode 4'. Dafür musst du aber wissen, wie man die eMMC-Partitionen per SSH/Linux löscht).*</sub>
  - Empfehlenswert ist ein zusätzliches **eMMC-Modul** (MKS eMMC Module), auf das du das neue Betriebssystem-Image und Mainline-Klipper installierst. So hast du immer ein Backup (den alten eMMC) eines funktionierenden Original-Druckers.
- Für '_Methode 2_' brauchst du eine ausreichend große **MicroSD-Karte**. Es ist *auch* möglich, alles von der SD-Karte laufen zu lassen und gar keinen eMMC zu verwenden.
- Für '_Methode 4_' brauchst du ein ausreichend langes **gewinkeltes USB-C-Kabel** (oder etwas Gleichwertiges), um das Board mit deinem Computer zu verbinden.
- Du brauchst einen ST-Link V2 (Mini) und die Software **STM32CubeProgrammer**, um die MCU-Firmware zu sichern und zu flashen.
- Die in dieser Anleitung verwendeten Dateien liegen gesammelt im GitHub-Ordner `/files-used/` [HIER](files-used/)
- Bearbeite die Dateien in dieser Anleitung bitte mit einem Texteditor wie [Notepad++](https://notepad-plus-plus.org/) (oder mit `nano` per SSH). So bleiben die Dateien im richtigen Format mit (Linux-)Zeilenenden und funktionieren wie gedacht. *Mit dem normalen Windows-Editor ist das nicht immer der Fall!*

### eMMC-Händler

[QIDI (USA/EU/UK/CA/JP/AU)](https://qidi3d.com/products/x-max-3-x-plus-3-x-smart-3-emmc-32g)

[Aliexpress (China)](https://www.aliexpress.us/item/3256807073480438.html)

[Kingroon (China)](https://kingroon.com/products/upgrade-32gb-emmc-module-for-kingroon-kp3s-pro-v2-and-klp1)
<br>
> [!NOTE]
> Je nach gekauftem Modell brauchst du zusätzlich einen MicroSD-Kartenleser. Folge der Anleitung, aber wo vom USB-Adapter die Rede ist, nimmst du deinen MicroSD-Kartenleser zusammen mit dem '**MICROSD TO EMMC ADAPTER**'.

# SCHRITT 1 - eMMC AUS DEM DRUCKER AUSBAUEN

> [!CAUTION]
> DRUCKER AUSSCHALTEN UND DEN NETZSTECKER ZIEHEN.

1. Leg den Drucker auf den Rücken, damit du an die Unterseite kommst.
2. Entferne die Metallplatte, indem du die 6 Schrauben löst.
3. Jetzt siehst du das eMMC-Modul auf dem Board. Löse die 2 Schrauben, die es halten, und nimm das eMMC-Modul vorsichtig heraus.
   - Merk dir, wie herum das eMMC-Modul eingesetzt war (_Tipp: Auf dem Board zeigt auch ein Pfeil, wie herum das Modul gehört_)

   ![Position des eMMC-Moduls auf dem Board](images/mainboard-emmc-location.jpg)

<br>

# SCHRITT 2 - SPEICHERMEDIUM BESCHREIBEN

> [!CAUTION]
> KEINE VERSION V3.0.0 ODER HÖHER VERWENDEN. BITTE V2.3.4 NEHMEN. <br>
> V3.0.0 WIRD NOCH GETESTET.. <br>

Lade zuerst das Linux-Image BIGTREETECH CB1 herunter (auch das Original-Image des Sovol SV08 basiert darauf): [https://github.com/bigtreetech/CB1](https://github.com/bigtreetech/CB1/releases/tag/V2.3.4)
>[!NOTE]
>Unabhängig vom Medium (SD-Karte oder eMMC) und seiner Größe vergrößert sich das BIGTREETECH-CB1-Image beim ersten Start auf die volle Größe des verwendeten Mediums.

Hier gibt es 3 Methoden:

**Methode 1**: Das CB1-Image direkt auf den eMMC schreiben und so verwenden.

**Methode 2**: Das CB1-Image auf eine SD-Karte schreiben und von dort auf den eMMC bringen.

_**Methode 3**: Alles von der SD-Karte laufen lassen und bei Methode 2, Punkt 2 aufhören._

_**Methode 4**: Das CB1-Image direkt auf den eMMC schreiben, indem du das Mainboard per USB-C-Kabel mit einem Computer verbindest._

> [!TIP]
> Bei manchen gibt es nach dem Schreiben mit Balena Etcher einen Fehler beim Booten, oder der Drucker bootet gar nicht. Einige hatten dann Erfolg, indem sie das Image stattdessen mit dem `Raspberry Pi Imager` geschrieben haben.

<br>

## METHODE 1: IMAGE DIREKT AUF DEN eMMC SCHREIBEN

1. Lade das **MINIMAL**-Image von BIGTREETECH herunter. Vorsicht, es gibt auch ein volles Image, auf dem schon eine unbekannte Klipper-Version installiert ist. Hier geht es lang: https://github.com/bigtreetech/CB1/releases/tag/V2.3.4
   - In diesem Beispiel verwendet: [CB1_Debian11_minimal_kernel5.16_20240319.img.xz](https://github.com/bigtreetech/CB1/releases/download/V2.3.4/CB1_Debian11_minimal_kernel5.16_20240319.img.xz)
2. Steck das eMMC-Modul in den USB-Adapter (auch hier auf die Richtung achten, auf dem Adapter ist ein Pfeil) und den USB-Adapter in deinen Computer.
3. _Jetzt ist ein guter Moment, `/home/sovol/printer_data/config/` für später zu sichern. (Zum Beispiel die `printer.cfg` wegen der Seriennummern `/dev/serial/by-id/usb-Klipper_stm32f103xe`. Steht dort etwas wie `/dev/ttyACM1`, keine Sorge, die vollständige Seriennummer ermitteln wir in **Schritt 7**)_.
4. Schreib das Image mit [BalenaEtcher](https://github.com/balena-io/etcher/releases) auf den eMMC
   - In diesem Beispiel verwendet: balenaEtcher-win32-x64-1.19.21.zip (portable Version, braucht keine Installation)
   - Balena Etcher öffnen<br>
     -> "Flash from file" wählen, das heruntergeladene CB1-Image auswählen<br>
     -> das eMMC-Laufwerk auswählen (z.B. Generic USB STORAGE DEVICE USB device)<br>
     -> Flash! (das löscht alles auf dem eMMC!)
5. Wenn das Schreiben fertig ist, kannst du BalenaEtcher schließen. Wenn alles geklappt hat, siehst du jetzt ein FAT-Laufwerk namens 'BOOT' (falls nicht, USB-Adapter auswerfen und wieder einstecken).

_Weiter geht es mit **SCHRITT 3**_

<br>

## METHODE 2: IMAGE AUF SD-KARTE -> eMMC

1. Lade das **MINIMAL**-Image von BIGTREETECH herunter (siehe Methode 1, Punkt 1).
   - In diesem Beispiel verwendet: [CB1_Debian11_minimal_kernel5.16_20240319.img.xz](https://github.com/bigtreetech/CB1/releases/download/V2.3.4/CB1_Debian11_minimal_kernel5.16_20240319.img.xz)

2. Schreib das Image mit [BalenaEtcher](https://github.com/balena-io/etcher/releases) auf die **SD-Karte**
   - In diesem Beispiel verwendet: balenaEtcher-win32-x64-1.19.21.zip (portable Version, braucht keine Installation)
   - Balena Etcher öffnen<br>
     -> "Flash from file" wählen, das heruntergeladene CB1-Image auswählen<br>
     -> die **SD-Karte** auswählen <br>
     -> Flash! (das löscht alles auf der SD-Karte!)<br>

> [!NOTE]
> _Am Rande: Wenn du willst, kannst du den Drucker an dieser Stelle auch einfach von der SD-Karte betreiben und den eMMC ganz weglassen (Methode 3). Nur damit du es weißt ;-)_

3. Steck das eMMC-Modul in den USB-Adapter (auch hier auf die Richtung achten, auf dem Adapter ist ein Pfeil) und den USB-Adapter in deinen Computer.<br>

4. _Jetzt ist ein guter Moment, `/home/sovol/printer_data/config/` für später zu sichern. (Zum Beispiel die `printer.cfg` wegen der Seriennummern `/dev/serial/by-id/usb-Klipper_stm32f103xe`. Steht dort etwas wie `/dev/ttyACM1`, keine Sorge, die vollständige Seriennummer ermitteln wir in **Schritt 7**)_

5. Wir müssen alle Partitionen vom eMMC löschen (das löscht alles auf dem eMMC!):
   - Öffne unter Windows die Eingabeaufforderung (Win-R -> cmd) und starte `diskpart` (Vorsicht mit diskpart, wir wollen nicht den falschen Datenträger löschen!)
   - In diskpart `list disk` eingeben und nachsehen, welcher Datenträger dein eMMC ist
   - In diskpart `select disk <nr>` eingeben, wobei <nr> die Nummer deines eMMC ist. Stell sicher, dass es wirklich der richtige Datenträger ist, bevor du weitermachst!
   - In diskpart `clean` eingeben, das löscht alles bzw. alle Partitionen auf dem eMMC.
   - Mit `exit` diskpart beenden

![Diskpart](images/haa/diskpart.jpg)

_Jetzt bitte mit **SCHRITT 3** weitermachen und danach hierher zurückkommen!_

6. Wenn alles geklappt hat, ist der Drucker von der SD-Karte gestartet, und es ist Zeit, alles auf den eMMC zu kopieren und ihn bootfähig zu machen.
   - Prüfe zuerst, ob der eMMC erkannt wird und verfügbar ist:
     - Mit dem Befehl `fdisk -l` solltest du mehrere Speichergeräte sehen, darunter den eMMC (_z.B. /dev/mmcblk1 für die SD-Karte und /dev/mmcblk2 für den eMMC_).
   - Den Befehl `sudo nand-sata-install` ausführen:
     - Die Option 'Boot from eMMC - system on eMMC' wählen.
   - Das legt eine Partition (ext4) auf dem eMMC an, formatiert sie und kopiert den kompletten Inhalt der SD-Karte auf den eMMC.
   - Wenn das fertig ist, den SV08 ausschalten, die SD-Karte entfernen und vom eMMC starten. Wenn alles geklappt hat, startet er jetzt vom eMMC, und du kannst mit **SCHRITT 4** weitermachen.

<br>

## METHODE 4: IMAGE PER USB-C-KABEL DIREKT AUF DEN eMMC SCHREIBEN

1. Lade das **MINIMAL**-Image von BIGTREETECH herunter. Vorsicht, es gibt auch ein volles Image, auf dem schon eine unbekannte Klipper-Version installiert ist. Hier geht es lang: https://github.com/bigtreetech/CB1/releases/tag/V2.3.4
   - In diesem Beispiel verwendet: [CB1_Debian11_minimal_kernel5.16_20240319.img.xz](https://github.com/bigtreetech/CB1/releases/download/V2.3.4/CB1_Debian11_minimal_kernel5.16_20240319.img.xz)
2. Setz den eMMC ins Mainboard ein.
3. Such die DIP-Schalter SW1 auf dem Mainboard und stell den DIP-Schalter auf FEL (also Schalter 1 auf ON).

   ![Position der DIP-Schalter auf dem Board](images/notatechguy3d/mainboard-dip-switches-location.png)

4. Steck ein gewinkeltes USB-C-Kabel in den Anschluss USB0 auf dem Mainboard.

   ![Position des USB0-Anschlusses auf dem Board](images/notatechguy3d/mainboard-USB0-location.png)

5. Steck das andere Ende des USB-Kabels in deinen Computer.

> [!NOTE]
> _Am Rande: Für mehr Zuverlässigkeit kannst du einen USB-Hub mit eigenem Netzteil dazwischen hängen._

6. Installiere mit [Zadig](https://zadig.akeo.ie/) einen universellen USB-Treiber für dein Mainboard:
   - Zadig öffnen<br>
     -> Im Menü "Options" den Punkt "List All Devices" aktivieren<br>
     ![List All Devices](images/notatechguy3d/zadig-list-all-devices.png)

     -> Dein Mainboard suchen, es erscheint wahrscheinlich als unbekanntes Gerät mit der USB-ID `1F3A EFE8`<br>
     ![Mainboard finden](images/notatechguy3d/zadig-find-your-mainboard.png)

     -> Treiber installieren<br>
7. Schalte das Mainboard mit den [Sunxi-tools](https://github.com/bigtreetech/sunxi-tools) in den USB-Geräte-Modus:
   - Repository herunterladen/klonen und den Inhalt in einen Ordner sunxi-tools entpacken
   - Unter Windows die Eingabeaufforderung öffnen (Win-R -> cmd) und `cd <pfad>` ausführen, wobei der Pfad der heruntergeladene sunxi-tools-Ordner ist
   - In der Eingabeaufforderung `sunxi-fel.exe uboot u-boot-sunxi-cb1-emmc.bin` ausführen, das sollte das Mainboard in den USB-Speicher-Modus schalten
8. _Jetzt ist ein guter Moment, `/home/sovol/printer_data/config/` für später zu sichern. (Zum Beispiel die `printer.cfg` wegen der Seriennummern `/dev/serial/by-id/usb-Klipper_stm32f103xe`. Steht dort etwas wie `/dev/ttyACM1`, keine Sorge, die vollständige Seriennummer ermitteln wir in **Schritt 7**)_.
9. Schreib das Image mit [BalenaEtcher](https://github.com/balena-io/etcher/releases) auf den eMMC
   - In diesem Beispiel verwendet: balenaEtcher-win32-x64-1.19.21.zip (portable Version, braucht keine Installation)
   - Balena Etcher öffnen<br>
     -> "Flash from file" wählen, das heruntergeladene CB1-Image auswählen<br>
     -> das eMMC-Laufwerk auswählen (z.B. Generic USB STORAGE DEVICE USB device)<br>
     -> Flash! (das löscht alles auf dem eMMC!)
10. Wenn das Schreiben fertig ist, BalenaEtcher schließen und den DIP-Schalter zurückstellen. Wenn alles geklappt hat, siehst du jetzt ein FAT-Laufwerk namens 'BOOT' (falls nicht, den USB-Speicher auswerfen und die Punkte 4, 5 und 7 wiederholen).

_Weiter geht es mit **SCHRITT 3**_

<br>

# SCHRITT 3 - BOARDENV.TXT ANPASSEN & WLAN EINRICHTEN

Damit das CB1-Image richtig eingerichtet wird, müssen wir eine Datei kopieren und ein paar Änderungen an der BoardEnv.txt vornehmen. Außerdem tragen wir in der system.cfg die WLAN-Zugangsdaten ein (falls der Drucker nicht per Kabel verbunden ist).

1. Kopiere die Datei `sun50i-h616-sovol-emmc.dtb` aus dem GitHub-Ordner `/files-used/dtb-files/` [HIER](files-used/dtb-files/) auf das Laufwerk 'BOOT' in den Ordner `/dtb/allwinner/`.
2. Mach auf dem Laufwerk 'BOOT' zur Sicherheit ein **BACKUP** der 'BoardEnv.txt' auf deine Festplatte.
3. Öffne die 'BoardEnv.txt' in deinem Texteditor.
4. Ersetze den Inhalt OBERHALB der Zeile `#--------#` (was darunter steht, BLEIBT) durch folgende Zeilen _(siehe Bild unten, grün = eingefügt, rot = nicht anfassen, so lassen)_:
   ```ini
   bootlogo=false
   overlay_prefix=sun50i-h616
   fdtfile=sun50i-h616-sovol-emmc
   console=display
   overlays=uart3
   overlays=ws2812
   overlays=spidev1_1
   ```
   Das sieht dann ungefähr so aus:<br>
   ![Inhalt der BoardEnv.txt](images/BoardEnv.txt.jpg)
  > [!NOTE]
  > <sub>**HINWEIS 1**: Mit bootlogo=false erscheinen die Linux-Bootmeldungen auf einem HDMI-Bildschirm. Mit bootlogo=true siehst du sie nur, wenn du eine Tastatur anschließt und eine Taste drückst.</sub><br>
  <sub>**HINWEIS 2**: `fdtfile=sun50i-h616-sovol-emmc` unterstützt sowohl eMMC als auch SD-Karte, bootet aber natürlich nur von einem davon (laut BTT-CB1-Doku hat die SD-Karte Vorrang vor dem eMMC, es gab aber auch Berichte über das Gegenteil; bootet er vom eMMC statt von der SD-Karte, sieh dir Hinweis 3 an, sorg dafür, dass der eMMC leer bzw. nicht bootfähig ist, oder bau ihn einfach aus).</sub><br>
  <sub>**HINWEIS 3**: Mit `fdtfile=sun50i-h616-sovol-emmc` und einer SD-Karte scheint er immer von der SD-Karte zu booten, nutzt aber (scheinbar zufällig) die Datenpartition entweder vom eMMC oder von der SD-Karte. Das prüfst du mit `lsblk`: Kommen `/boot` und `/` beide von der SD-Karte? Wenn nicht, ausschalten, neu starten und erneut prüfen. Du kannst auch `fdtfile=sun50i-h616-biqu-sd` verwenden, um die SD-Karte zu erzwingen, verlierst dann aber die eMMC-Unterstützung.</sub><br>


- Speichere die geänderte BoardEnv.txt!

5. Trag die WLAN-Zugangsdaten in der 'system.cfg' ein.

> [!NOTE]
> Enthält dein WLAN-Passwort das Sonderzeichen `$`, solltest du es mit einem vorangestellten `\` maskieren. Die Bash, die die system.cfg einliest, interpretiert das `$` sonst und verändert das Passwort. Ein WIFI_PASSWD `1$234` gehört also als `1\$234` in die system.cfg.

   - Optional: die Zeile mit dem Hostnamen einkommentieren und als Hostnamen z.B. "SV08" eintragen
   - Änderungen an der system.cfg speichern


> [!IMPORTANT]
> Wenn du einen HDMI-Bildschirm verwendest, musst du die Bildschirmdrehung auf "inverted" stellen.


6. Wirf den USB-Adapter am Computer aus, setz den eMMC (und bei _Methode 2_ die **SD-Karte**) wieder in den Drucker ein und starte ihn, dann:
   - Per SSH mit dem Drucker verbinden (IP-Adresse im Router nachsehen oder den eingestellten Hostnamen verwenden), Benutzer/Passwort: **biqu/biqu**
   - Wenn alles stimmt, startet der Drucker sauber, du kommst per SSH drauf, bist mit diesem Schritt fertig und kannst Mainline-Klipper installieren. Oder du machst mit _**Methode 2**, Punkt 6_ weiter und bringst das System auf den eMMC!

> [!NOTE]
> Die Meldung 'system booting..' auf dem Display ist nur ein Startbild, kein echter Hinweis, dass das System noch bootet. _Erst wenn Klipper das Display richtig ansteuert, verschwindet die Meldung bzw. das Bild._ Da wir aber gerade ein frisches Image _ohne Klipper_ (und erst recht ohne Display-Config) aufgespielt haben, passiert das nie, und das Display zeigt weiter, dass es bootet. Schau im Router nach, ob der Drucker eine IP-Adresse bekommen hat, oder prüf an einem HDMI-Bildschirm, ob er tatsächlich gestartet ist.

<br>

# SCHRITT 4 - MAINLINE-KLIPPER INSTALLIEREN

Jetzt wird's spannend! Wir installieren KIAUH, Klipper, Moonraker usw. Verbinde dich per SSH (biqu/biqu) mit dem Drucker und führ die folgenden Schritte aus.<br>
<sub>Dafür brauchst du eine stabile Verbindung, weil alles heruntergeladen wird.</sub>
> [!IMPORTANT]
> Debian 11 (bullseye) wird nicht mehr unterstützt, deshalb funktionieren die APT-Spiegelserver des CB1-Images nicht mehr. Ersetze vorher `/etc/apt/sources.list` durch die archivierten Debian-Server:
> ```bash
> sudo nano /etc/apt/sources.list
> ```
> Ersetze den Inhalt durch Folgendes:
> ```
> deb [check-valid-until=no] http://archive.debian.org/debian bullseye main contrib non-free
> deb [check-valid-until=no] http://archive.debian.org/debian bullseye-updates main contrib non-free
> deb [check-valid-until=no] http://archive.debian.org/debian bullseye-backports main contrib non-free
> deb [check-valid-until=no] http://archive.debian.org/debian-security bullseye-security main contrib non-free
> ```
> Mit STRG-X (`Yes, <Enter>`) speichern. Dann mit den Schritten unten weitermachen.

1. Zuerst aktualisieren wir das Betriebssystem:<br>

   ```bash
   sudo apt update && sudo apt upgrade
   ```

2. Dann installieren wir git (ist eventuell schon da) und KIAUH mit folgenden Befehlen:

   ```bash
   sudo apt-get update && sudo apt-get install git -y
   ```

   ```bash
   cd ~ && git clone https://github.com/dw-0/kiauh.git
   ```

3. KIAUH mit folgendem Befehl starten:

   ```bash
   ./kiauh/kiauh.sh
   ```

4. Installiere per KIAUH Klipper, Moonraker, Mainsail und Crowsnest (in dieser Reihenfolge, _beachte auch den Hinweis unten_).

   - Also KIAUH starten, Option **'1) [Install]'** wählen und diese Pakete installieren (_Standardoptionen, empfohlene Makros herunterladen: **Ja**_ - der Installer in Schritt 8 braucht die `mainsail.cfg`, die dabei angelegt wird).
   - Die Crowsnest-Installation fragt, ob der Drucker neu gestartet werden soll, mach das jetzt (außer du hast einen HDMI-Bildschirm und willst KlipperScreen nutzen, dann kannst du das vor dem Neustart auch noch installieren).

> [!IMPORTANT]
> Stand **2025-04-28** gibt es bei der Klipper-Installation offenbar einen Abhängigkeitsfehler. Bricht deine Klipper-Installation mit `[ERROR] Error installing Python requirements: Installing Python requirements failed! [ERROR] Klipper installation failed!` ab, umgehst du das so und machst danach normal weiter:
> 1. Klipper ganz normal mit KIAUH installieren und mit dem Fehler oben enden lassen.
> 2. KIAUH beenden und folgende Befehle ausführen:
> ```
> rm -rf ~/.cache
> ~/klippy-env/bin/pip3 install pyserial aenum wrapt pycparser markupsafe greenlet python-can Jinja2 cffi
> ```
> 3. Dann Klipper mit KIAUH (neu) installieren: Bei der Frage, ob das Repository neu geklont und überschrieben werden soll, **Ja** wählen, bei `Virtualenv already exists. Re-create?` **Nein**. Jetzt sollte die Installation ohne Fehler durchlaufen.
> 4. Gibt es danach bei der Moonraker-Installation einen DEPRECATED-Fehler und Moonraker ist nur halb installiert: einfach noch einmal mit KIAUH installieren (alles überschreiben), beim zweiten Mal sollte es klappen.

> [!NOTE]
> Numpy (für den Input Shaper) und Moonraker-timelapse musst du nicht von Hand installieren, das macht der Installer in **Schritt 8**.

5. Jetzt ist Mainline-Klipper mit der Weboberfläche Mainsail installiert!
   - Falls du nach der Crowsnest-Installation noch nicht neu gestartet hast:<br> `sudo reboot`
   - Nach dem Neustart rufst du im Browser die Mainsail-Oberfläche auf (über IP-Adresse oder Hostnamen) und prüfst, ob sie läuft.
   - Mainsail zeigt einen Klipper-Fehler, weil es noch keine Druckerkonfiguration gibt. Das ist so gewollt: Die Konfiguration kommt in **Schritt 8**, nachdem die MCUs ihre neue Firmware haben.

<br>

# SCHRITT 5 - ORIGINAL-FIRMWARE SICHERN

> [!IMPORTANT]
> Wenn du den ST-Link an den Drucker anschließt, muss der Drucker **AUS** sein. Die MCU wird dann über den ST-Link mit Strom versorgt.

Es ist wichtig, die aktuelle (Original-)Firmware zu sichern. So kannst du jederzeit zum Auslieferungszustand zurück. Diese Schritte gelten für die Druckkopf-MCU und für die Mainboard-MCU.

1. Stell zuerst sicher, dass dein ST-Link mit der Software STM32CubeProgrammer richtig installiert ist.

   - Die Software STM32CubeProgrammer gibt es hier: https://www.st.com/en/development-tools/stm32cubeprog.html#st-get-software
   - Installiere die Software und prüf, ob der ST-Link richtig erkannt wird: Die Software sollte direkt unter dem CONNECT-Knopf die Seriennummer deines ST-Link anzeigen (falls nicht, auf den kleinen Aktualisieren-Knopf klicken).

> [!TIP]
> Dein (Nachbau-)ST-Link funktioniert nicht mit STM32CubeProgrammer und zeigt z.B. nur eine einstellige Seriennummer? Probier stattdessen das ältere Flash-Programm, das gibt es hier: https://www.st.com/en/development-tools/stsw-link004.html. Die Schritte unten beschreiben den STM32CubeProgrammer, im alten Programm läuft es weitgehend gleich, nur mit anderer Oberfläche.

> [!TIP]
> Du verwendest STM32CubeProgrammer unter Linux und bekommst keine Verbindung zum ST-Link? Dann musst du eventuell einen häufigen Installationsfehler von Hand beheben, siehe diese [Anleitung](https://stackoverflow.com/a/69414727/6910451).

2. _Schalte den Drucker AUS_ und zieh den ST-Link vom Computer ab. Dann schließ den ST-Link an dein Board an (Druckkopf oder Mainboard).

   - ACHTE AUF DIE RICHTIGE VERKABELUNG, die Belegung auf den Boards ist (SV08 -> ST-Link Mini):
     - 3V3 -> 3.3V
     - IO -> SWDIO
     - CK -> SWCLK
     - G -> GND
   - Die Belegung am Adapter findest du in der Anleitung deines ST-Link (nicht alle ST-Links haben genau dieselbe Belegung)!

> [!CAUTION]
> Achte auf die Ausrichtung der Boards in den Bildern unten und richte dich nach den Beschriftungen auf Mainboard und Druckkopf!

  ### Position der ST-Link-Pins auf dem Mainboard:
  ![Position der ST-Link-Pins auf dem Mainboard](images/board-stlink-pins-v2.jpg)

  ### Position der ST-Link-Pins auf dem Druckkopf:
  ![Position der ST-Link-Pins auf dem Druckkopf](images/toolhead-stlink-pins-v2.jpg)

3. Steck den ST-Link in den Computer (_der Drucker bleibt aus_), öffne STM32CubeProgrammer und klick auf CONNECT. Die Verbindung sollte stehen, und in der Mitte erscheinen Speicherinhalte.
4. Wähle im Menü `Read` den Punkt `Read all`. Das liest alles aus und stellt die richtige Größe zum Speichern ein.

![Read all](images/stlink-firmware-read-all.jpg)

5. Wähle im Menü `Read` den Punkt `Save As ..` und speichere die aktuelle Firmware (z.B. _toolhead_original_firmware.bin_ oder _mainboard_original_firmware.bin_).

![Save As](images/stlink-firmware-save-as.jpg)

> [!CAUTION]
> Die Firmware-Sicherung muss für den Druckkopf mindestens 128k groß sein, für das Mainboard 512k. Ist sie nur 1 Kilobyte groß, ist sie zu klein, und du kommst damit nicht zur alten Firmware zurück.
> Falls das schon passiert ist: Hier gibt es <a href="firmware-backups">Firmware-Sicherungen</a> von Druckkopf und Mainboard (Drucker an die EU ausgeliefert am 2024-06-28). Benutzung auf eigene Gefahr.

<br>

# SCHRITT 6 - KATAPULT-BOOTLOADER FLASHEN

> [!IMPORTANT]
> Wenn du den ST-Link an den Drucker anschließt, muss der Drucker AUS sein. Die MCU wird dann über den ST-Link mit Strom versorgt.<br>
> Stell außerdem sicher, dass dein ST-Link die neueste Firmware hat, dafür gibt es in STM32CubeProgrammer den Knopf 'Firmware upgrade'.

> [!NOTE]
> Nach dem Flashen von Katapult startet der Drucker stumm: keine Lüfter, kein Licht, kein Display beim Booten. Keine Panik, das ist normal. In Schritt 7 holen wir diese Funktionen zurück.

Um uns das Leben in Zukunft leichter zu machen, flashen wir Katapult auf die MCUs (sowohl auf die Mainboard-MCU _als auch_ auf die Druckkopf-MCU). Katapult ist ein Bootloader, mit dem der Host die Klipper-Firmware ohne ST-Link über CAN-Bus, USB oder UART flashen kann.

1. Schalte den Drucker ein, verbinde dich per SSH (biqu/biqu) und installiere Katapult:

   - Mit diesem Befehl installierst du Katapult: <br>

   ```bash
   cd ~ && git clone https://github.com/Arksine/katapult
   ```

   - pyserial installieren _(brauchen wir später zum Flashen der Firmware)_<br>

   ```bash
   pip3 install pyserial
   ```

2. Wenn das fertig ist: <br>

   ```bash
   cd ~/katapult && make menuconfig
   ```

   Im menuconfig folgende Optionen wählen:<br>
   ![Katapult-Einstellungen im menuconfig](images/katapult-firmware-settings.jpg)<br>

3. Mit Q beenden und die Änderungen speichern.<br>
4. Mit diesen Befehlen die Firmware bauen (_katapult.bin_):<br>

   ```bash
   make clean
   make
   ```

5. Hol dir die Datei `~/katapult/out/katapult.bin` (z.B. mit einem SFTP-Programm wie WinSCP) und speichere sie auf dem Computer. Diese Katapult-Firmware passt für Druckkopf und Mainboard.
6. _Schalte den Drucker wieder AUS_, steck den ST-Link danach wieder in den Computer, starte STM32CubeProgrammer und klick auf CONNECT.
7. Wenn die Verbindung steht, links den Reiter 'Erasing & Programming' öffnen und einen `Full chip erase` _von Hand_ ausführen (**nicht** nur im automatischen Modus).

![Full chip erase](images/haa/STM32/Etape4.png)

8. Jetzt wird geflasht! Zurück zum Reiter 'Memory & File editing', auf 'Open file' klicken, die `katapult.bin` auswählen und dann mit dem Knopf 'Download' die Firmware schreiben.<br>
<sub>Alternativ kannst du die Firmware im Reiter 'Erasing & Programming' schreiben: Mit 'Browse' die `katapult.bin` auswählen und dann mit 'Start Programming' schreiben.</sub>

![Open file](images/haa/STM32/Etape5.png)<br>

![Download](images/haa/STM32/Etape6.png)<br>

Fertig! Der Katapult-Bootloader ist auf der MCU! Klick auf 'Disconnect' und zieh den ST-Link vom Computer und vom Board ab. Mach das für die Druckkopf-MCU und für die Mainboard-MCU.

<br>

# SCHRITT 7 - KLIPPER-FIRMWARE AUF DIE MCUs FLASHEN

> [!NOTE]
> Die Standard-Klipper-Firmware funktioniert auf der Druckkopf-MCU und auf der Mainboard-MCU. Sovol hatte ursprünglich mehrere Änderungen am Quellcode `stm32f1.c` vorgenommen, die sind aber nicht nötig. **Nur startet der Drucker jetzt stumm: keine Lüfter, kein Licht, kein Display beim Booten.** Einen Teil davon KANNST du zurückholen, indem du GPIO-Pins beim Start aktivierst, siehe die Hinweise unten beim menuconfig.

> [!TIP]
> Für spätere Klipper-Firmware-Updates musst du, nachdem du die Schritte unten einmal erledigt hast, nur noch das Skript aus Schritt `7.7` ausführen.

Zeit, die Klipper-Firmware zu bauen und zu flashen! Künftig brauchst du diesen Schritt nur, wenn du die Klipper-Firmware aktualisieren willst. _Dieser Abschnitt setzt voraus, dass **Katapult** schon geflasht und **pyserial** (Schritt 6.1) installiert ist._

1. Schalte den Drucker ein und verbinde dich per SSH (biqu/biqu).

2. Ermittle die Seriennummern beider MCUs. Wir brauchen nur den Teil nach `usb-Klipper_stm32f103xe_` (bzw. `usb-Katapult_stm32f103xe_`), unten rot eingekreist. Schreib dir auf, welche zum **Mainboard** (`[mcu]`) und welche zum **Druckkopf** (`[mcu extra_mcu]`) gehört, der Installer in Schritt 8 fragt danach.

![Seriennummern in der printer.cfg](images/haa/haa_printercfg.jpg)

- Stehen in deiner gesicherten Original-printer.cfg (siehe Voraussetzungen) solche Seriennummern, kannst du sie von dort nehmen. Steht dort stattdessen `ttyACM0`/`ttyACM1`, etwa so:

![ttyACM in der printer.cfg](images/haa/haa_printercfg_tty.jpg)

oder hast du keine Sicherung, ermittelst du die vollständigen Seriennummern mit diesem Befehl. **UND LIES DIE WARNUNG UNTEN!**<br>

```bash
ls -la /dev/serial/by-id/
```

Das sieht dann so aus:

![Ausgabe von ls -la /dev/serial/by-id/](images/haa/haa_lsla.jpg)

Der blaue Teil ist die Seriennummer (_Groß-/Kleinschreibung beachten_). In der printer.cfg sieht das dann so aus (mit deinen Ziffern):

![Seriennummern in der printer.cfg](images/haa/haa_printercfg2.jpg)

> [!WARNING]
> **WARNUNG**: Wenn du die Seriennummern von `mcu` und `extra_mcu` versehentlich vertauschst, kann Schlimmes passieren. _**DIE HEIZUNG GEHT AUF VOLLE LEISTUNG!**_ Das willst du nicht.
<br><br>
Verwende außerdem **NIEMALS** *ttyACM0* und *ttyACM1* als Seriennummer. Die sind nicht fest, können sich vertauschen und genau diesen gefährlichen Effekt auslösen. Genau deshalb wollen wir die lange (feste) Seriennummer.
<br><br>
Um 100 % sicher zu sein, dass jede Seriennummer zur richtigen MCU gehört, prüf die Seriennummern mit `ls /dev/serial/by-id/` und **zieh** dann den USB-Stecker am **Druckkopf** ab (_siehe Bild unten_). Führ `ls /dev/serial/by-id/` erneut aus: Die Seriennummer, die noch da ist, ist deine `mcu`, die verschwundene ist deine `extra_mcu`. Steck den Stecker wieder ein und bestätige mit einem weiteren `ls /dev/serial/by-id/`, dass du `mcu` und `extra_mcu` richtig zugeordnet hast.

![USB-Stecker am Druckkopf abziehen](images/toolhead-disconnect-usb.jpg)

> [!NOTE]
> Die richtige Seriennummer unserer MCUs in der printer.cfg beginnt immer mit **`usb-Klipper_stm32f103xe_`** (Groß-/Kleinschreibung beachten). Findest du bei _`ls /dev/serial/by-id/`_ nur Seriennummern, die mit `usb-Katapult_stm32f103xe_` beginnen, ist das in Ordnung: Die MCU ist dann im Bootloader-Modus und bereit für die Klipper-Firmware. Die Nummer dahinter bleibt gleich. Nach dem Flashen der Klipper-Firmware heißt sie `usb-Klipper_stm32f103xe_`.

3. Lade das Skript [Automatic MCU script update](<Automatic MCU script update/>) herunter und kopiere es auf dem Drucker in den Ordner `~/klipper`.

4. Öffne es mit nano und trag die ID jeder MCU ein, die du in [2](#schritt-7---klipper-firmware-auf-die-mcus-flashen) aufgeschrieben hast:
```batch
sudo nano ~/klipper/update_klipper_mcus_sv08.sh
```
- Ersetze XXXXXXX durch die Seriennummer von `[mcu]` (Mainboard) und YYYYYYY durch die von `[extra mcu]` (Druckkopf):

*printer.cfg<br>*
![Seriennummern in der printer.cfg](images/haa/haa_amu_printercfg.jpg)

*update_klipper_mcus_sv08.sh<br>*
```bash
#Replace each XXXXXXXX and YYYYYYYY serial number with the one you find in your printer.cfg file (we only need the part after 'usb-Klipper_stm32f103xe_')
#HOSTSERIAL is found under [mcu]
#TOOLHEADSERIAL is found under [extra mcu]

# I'm a string, so I look like: HOSTSERIAL='XXXXXXXX'
HOSTSERIAL='XXXXXXXX'

# I'm an array so I look like: TOOLHEADSERIAL=('YYYYYYY')
# For multiple serials/toolheads use (mind the space in between items!): TOOLHEADSERIAL=('YYYYYYYY1' 'YYYYYYYY2' 'YYYYYYY3')
TOOLHEADSERIAL=('YYYYYYY')
```
- Im Skript steht dann zum Beispiel:

```bash
#Replace each XXXXXXXX and YYYYYYYY serial number with the one you find in your printer.cfg file (we only need the part after 'usb-Klipper_stm32f103xe_')
#HOSTSERIAL is found under [mcu]
#TOOLHEADSERIAL is found under [extra mcu]

# I'm a string, so I look like: HOSTSERIAL='XXXXXXXX'
HOSTSERIAL='32FFD9054747363035861857-if00'

# I'm an array so I look like: TOOLHEADSERIAL=('YYYYYYY')
# For multiple serials/toolheads use (mind the space in between items!): TOOLHEADSERIAL=('YYYYYYYY1' 'YYYYYYYY2' 'YYYYYYY3')
TOOLHEADSERIAL=('50FF6C068367515511180667-if00')
```
5. Datei mit `Strg + X` speichern.

6. Skript ausführbar machen:
```bash
chmod +x ~/klipper/update_klipper_mcus_sv08.sh
```

7. Jetzt kannst du das Skript so starten:
```bash
cd "$HOME/klipper" && ./update_klipper_mcus_sv08.sh
```
> [!NOTE]
> Einige berichten, dass nichts Klipper beschäftigen sollte (z.B. eine offene Mainsail/Fluidd-Seite oder eine App, die auf Klipper zugreift), sonst bleibt das Flashen bei 'Attempting to connect to bootloader' hängen.
> Für die besten Erfolgschancen also Mainsail und alles andere schließen, was den Drucker/Klipper beschäftigen könnte, eventuell sogar vor dem Flashen neu starten und dann das Update-Skript ausführen.

8. Im Menü des MCU-Updaters Option 1 'HOST MCU' wählen. Im menuconfig für den **`HOST`** folgende Option(en) wählen und in der letzten Zeile `PA1,PA3` eintragen (_GPIO-Pins_, falls du _MCU-Lüfter und Licht_ beim Booten willst). Dann mit Q beenden und speichern. Den weiteren Anweisungen folgen und die HOST-MCU flashen.<br>

![menuconfig für die Host-MCU](images/haa/haa_host_menuconfig.jpg)

> [!NOTE]
> <sub>Da wir Katapult als Bootloader verwenden, unbedingt den Bootloader-Offset von 8 KiB einstellen.</sub><br>

9. Im Menü des MCU-Updaters Option 2 'TOOLHEAD MCU(S)' wählen. Im menuconfig für den **`TOOLHEAD`** folgende Option(en) wählen und in der letzten Zeile `PA6` eintragen (_GPIO-Pins_, falls der _Hotend-Lüfter_ beim Booten laufen soll). Dann mit Q beenden und speichern. Den weiteren Anweisungen folgen und die TOOLHEAD-MCU flashen.<br>

![menuconfig für die Druckkopf-MCU](images/haa/haa_toolhead_menuconfig.jpg)

> [!NOTE]
> <sub>Da wir Katapult als Bootloader verwenden, unbedingt den Bootloader-Offset von 8 KiB einstellen.</sub><br>

![Automatisches MCU-Update](images/haa/haa_automatic_mcu_update.jpg)

10. Fertig! Die Klipper-Firmware auf beiden MCUs ist aktualisiert.

11. Drucker neu starten:
```bash
sudo shutdown -r now
```

12. Prüf nach dem Neustart, dass beide MCUs jetzt als `usb-Klipper_stm32f103xe_...` erscheinen:
```bash
ls /dev/serial/by-id/
```

<br>

# SCHRITT 8 - DRUCKERKONFIGURATION INSTALLIEREN UND KALIBRIEREN

Dieser Schritt ersetzt die Konfiguration von Hand (Configs und Sovol-Addons kopieren) aus der Original-Anleitung. Details, Befehle und Hintergründe: [sv08-loadcell/README.md](sv08-loadcell/README.md).

1. Verbinde dich per SSH (biqu/biqu) mit dem Drucker und führ als normaler Benutzer (**nicht** mit sudo) aus:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/Jane0899/Sovol-SV08-Mainline/main/sv08-loadcell/get.sh | bash
   ```

   Das klont dieses Repository nach `~/Sovol-SV08-Mainline` und startet den Installer. Der Installer:
   - prüft Klipper, Moonraker, Mainsail und dass beide MCUs Klipper-Firmware haben,
   - **sichert** alte Configs und Sovol-Reste nach `~/printer_data/backup/sv08-loadcell-<Datum>/` und räumt sie weg,
   - installiert die Druckerkonfiguration, das Klipper-Modul, Numpy (Input Shaper) und Moonraker-timelapse,
   - fragt, welche MCU das **Mainboard** und welche der **Druckkopf** ist (deine Notizen aus Schritt 7.2), außer er kann es aus einer vorhandenen printer.cfg lesen,
   - härtet auf einem ehemaligen Sovol-Werks-Image Sovols USB-Automount und fragt, was mit G-Code-Dateien auf einem USB-Stick passieren soll,
   - trägt den Updater in Moonraker ein, damit künftige Updates in Mainsail erscheinen (Maschine -> Update Manager),
   - startet Klipper und Moonraker neu.

2. Räum das Bett leer und leg ein Blatt Papier bereit. Öffne in Mainsail die Konsole und gib ein:

   ```
   CALIBRATE_SV08
   ```

   Der Assistent führt dich mit Dialogen in Mainsail durch: Sensor-Check, Homing + QGL, Messreihen für induktive Probe und Wägezelle, Düsenreinigung, Z-Nullpunkt, Papiertest und Input Shaper. Das dauert etwa 30–40 Minuten. Am Ende speichert **Speichern + Neustart** alle Werte. Für eine andere Drucktemperatur: `CALIBRATE_SV08 TEMP=240`.

3. Start-G-Code im Slicer anpassen:

   - In OrcaSlicer/PrusaSlicer die Druckereinstellungen öffnen:<br>
     -> Maschinen-G-Code<br>
     -> Maschinen-Start-G-Code<br>
     -> In OrcaSlicer die Zeile 'START_PRINT' so ändern:<br>

     ```gcode
     START_PRINT EXTRUDER_TEMP=[nozzle_temperature_initial_layer] BED_TEMP=[bed_temperature_initial_layer_single]
     ```

     -> In PrusaSlicer/SuperSlicer die Zeile 'START_PRINT' so ändern:<br>
     ```gcode
     START_PRINT EXTRUDER_TEMP=[first_layer_temperature] BED_TEMP=[first_layer_bed_temperature]
     ```
   - Maschinen-End-G-Code: `END_PRINT`
   - Du willst vor dem Druck **durchwärmen** (Heatsoak)? Häng `HEATSOAK=1 SOAKTIME=15` (Minuten) an die START_PRINT-Zeile an.
   - Für Zeitraffer prüfen, ob im 'G-Code vor dem Schichtwechsel' (Before layer change G-code) `TIMELAPSE_TAKE_FRAME` steht. Den Zeitraffer selbst stellst du in den Mainsail-Einstellungen ein.

4. Optional: die Webcam in Mainsail hinzufügen (Einstellungen > Webcams > Webcam hinzufügen).

5. Viel Spaß mit Mainline-Klipper!

> [!NOTE]
> Die Dateien in `/files-used/config/` und `/files-used/sovol-addons/` (Konfiguration von Hand aus der Original-Anleitung) brauchst du mit diesem Fork nicht.

<br>

# DANK & MITMACHEN

Großen Dank an alle auf den (offiziellen und inoffiziellen) Sovol-Discords, die bei diesem Projekt geholfen oder irgendwie mitgemacht haben.
Besonderer Dank an: ss1gohan13, michrech, Zappes, cluless, Haagel, Froh - _ihr seid spitze!_

Du möchtest zu diesem Projekt bzw. dieser Anleitung beitragen? Super! Erstell einen Pull Request oder ein Issue, dann kann es in die Anleitung aufgenommen werden.

<br>

# Haftungsausschluss

Diese Anleitung und alle Änderungen sind nach bestem Wissen entstanden, aber am Ende liegt es in deiner Verantwortung und _nur in deiner Verantwortung_, diese Änderungen an deinem Drucker vorzunehmen. Weder der Autor noch die Mitwirkenden noch Sovol haften, wenn etwas schiefgeht, kaputtgeht, Feuer fängt oder den Dritten Weltkrieg auslöst. Du machst das auf eigene Gefahr!
