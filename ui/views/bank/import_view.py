# ui/views/bank/import_view.py
#
# BankImportView — banki .UMS fájlok importálása.
#
# Az UMS (Universal Message Standard) a bank által exportált, pontosvesszővel
# tagolt szövegfájl formátum (windows-1250 kódolással), amely 38 mezőt tartalmaz.
#
# Folyamat:
#   1. Fájlok kiválasztása (.ums) → beolvasás pandas DataFrame-be
#   2. Dátumjavítás (Column4, Column14): rövid éves formátum → 4 jegyű év
#   3. Szállítói nevek normalizálása (BUDAPEST 15 PP, MAGYAR POSTA, FURGEFUTAR)
#   4. Validálás: oszlopszám, kötelező mezők, dátumformátum, decimális összeg
#   5. Mentés az adatbázis Bank_stage táblájába (bulk insert)
#
# A BaseImportView kezeli az UI logika nagy részét (fájllista, gombok, progress).
# Ez az osztály csak az UMS-specifikus részt valósítja meg.

import os
import pandas as pd
from PySide6.QtWidgets import QFileDialog, QMessageBox, QApplication
from PySide6.QtCore import Qt
from datetime import datetime
from ui.dialogs.file_import_progress import ProgressDialog
from ui.views.base_import_view import BaseImportView


class BankImportView(BaseImportView):
    """Banki .UMS fájlok importálási nézete.

    Több fájl egyszerre betölthető (akkumuláló mód: minden betöltés hozzáad
    a meglévő adatokhoz, nem felülírja azokat). Egy fájl kétszer nem tölthető be.
    """

    def __init__(self):
        super().__init__()
        self.setup_ui(
            "Banki adatok importálása", import_button_label="Fájlok kiválasztása"
        )

        self.df_all = pd.DataFrame()     # az összes betöltött fájl összesített adatai
        self.loaded_files = set()        # már betöltött fájlok abszolút útvonalai (duplikáció szűrés)

    # -------------------------------------------------------------------------
    # BaseImportView kötelező implementációk
    # -------------------------------------------------------------------------

    def load_files(self):
        """Fájlválasztó dialógus megnyitása, UMS fájlok beolvasása.

        Duplikáció ellenőrzés: ha egy fájl már be van töltve, figyelmeztető
        üzenetet jelenít meg, de az újakat továbbra is betölti.

        Az UMS fájl formátuma:
          - Elválasztó: pontosvessző (;)
          - Kódolás: windows-1250 (közép-európai karakterek)
          - Fejléc: nincs — az oszlopok Column1..Column38 névvel kapnak nevet
          - Ha egy fájlban kevesebb mint 38 oszlop van, üres oszlopokkal egészítjük ki
        """
        files, _ = QFileDialog.getOpenFileNames(
            self, "Válassz .UMS fájlokat", "", "UMS fájlok (*.ums)"
        )

        if not files:
            return

        # Szétválasztja a már betöltött és az új fájlokat
        duplicates = [f for f in files if f in self.loaded_files]
        new_files = [f for f in files if f not in self.loaded_files]

        if not new_files:
            if duplicates:
                QMessageBox.warning(
                    self,
                    "Ismétlődő fájlok",
                    f"A következő fájl(ok) már be lettek olvasva:\n"
                    + "\n".join(os.path.basename(f) for f in duplicates),
                )
            return

        all_new_data = []
        self.loaded_files.update(new_files)

        # Progress dialógus megjelenítése beolvasás közben
        self.progress_dialog = ProgressDialog()
        self.progress_dialog.show()
        QApplication.processEvents()

        for file in new_files:
            filename = os.path.basename(file)
            self.loaded_files.add(file)
            self.file_list_widget.addItem(filename)

            try:
                df = pd.read_csv(
                    file,
                    sep=";",                    # pontosvessző elválasztó
                    header=None,                # nincs fejléc sor
                    encoding="windows-1250",    # közép-európai kódolás
                    dtype=str,                  # minden oszlop string (nem konvertál)
                )
                # Ha kevesebb mint 38 oszlop van, üres oszlopokkal töltjük fel
                while df.shape[1] < 38:
                    df[df.shape[1]] = ""
                # Egységes oszlopnév: Column1..Column38
                df.columns = [f"Column{i+1}" for i in range(38)]
                all_new_data.append(df)

            except Exception as e:
                QMessageBox.warning(
                    self, "Hiba", f"{filename} beolvasása sikertelen:\n{str(e)}"
                )

        if not all_new_data:
            QMessageBox.information(
                self, "Nincs adat", "Nem található beolvasható .UMS fájl."
            )
            return

        # Az összes új fájl adatait egybefűzzük
        new_df = pd.concat(all_new_data, ignore_index=True)

        # Dátumjavítás: Column4 és Column14 rövidített dátum formátuma (dd.mm.yy)
        # → teljes évszámos formátumra (yyyy.mm.dd) alakítjuk
        for col in ["Column4", "Column14"]:
            if col in new_df.columns:
                new_df[col] = new_df[col].apply(self.fix_short_date)

        # Szállítói nevek normalizálása: Column30 + Column31 összefűzésből azonosítja
        # és a Column30-ba helyezi a normalizált nevet, Column31-et törli
        if "Column30" in new_df.columns and "Column31" in new_df.columns:
            combined = (
                new_df["Column30"].fillna("") + "" + new_df["Column31"].fillna("")
            )
            mask = combined.str.contains("BUDAPEST 15 PP", case=False, na=False)
            new_df.loc[mask, "Column30"] = "BUDAPEST 15 PP"

        if "Column30" in new_df.columns and "Column31" in new_df.columns:
            combined = (
                new_df["Column30"].fillna("") + "" + new_df["Column31"].fillna("")
            )
            mask = combined.str.contains("MAGYAR POSTA 1870", case=False, na=False)
            new_df.loc[mask, "Column30"] = "MAGYAR POSTA 1870"
            new_df.loc[mask, "Column31"] = ""

        if "Column30" in new_df.columns and "Column31" in new_df.columns:
            combined = (
                new_df["Column30"].fillna("") + "" + new_df["Column31"].fillna("")
            )
            mask = combined.str.contains("FURGEFUTAR.HU", case=False, na=False)
            new_df.loc[mask, "Column30"] = "FURGEFUTAR.HU"
            new_df.loc[mask, "Column31"] = ""

        # Hozzáfűzzük a meglévő adatokhoz (akkumuláló mód)
        self.df_all = pd.concat([self.df_all, new_df], ignore_index=True)

        # Gombállapotok frissítése (BaseImportView)
        self._on_file_loaded()

        # Column11 (összeg) megjelenítési formázó: "1234.56" → "1 234,56"
        def format_thousands(val):
            try:
                number = float(str(val).replace(",", "."))
                return f"{number:,.2f}".replace(",", " ").replace(".", ",")
            except ValueError:
                return val

        self.update_table_view(
            self.df_all.fillna(""),
            formatters={"Column11": format_thousands},
            alignments={"Column11": Qt.AlignRight | Qt.AlignVCenter},
        )

        if self.progress_dialog:
            self.progress_dialog.accept()
            self.progress_dialog = None

        # Duplikátumokra figyelmeztetés (ha volt ilyen a kiválasztásban)
        if duplicates:
            QMessageBox.warning(
                self,
                "Ismétlődő fájlok",
                f"A következő fájl(ok) már be lettek olvasva:\n"
                + "\n".join(os.path.basename(f) for f in duplicates),
            )

    def get_data_for_save(self) -> pd.DataFrame:
        """Visszaadja az összes betöltött adat DataFrame-jét."""
        return self.df_all

    def validate_for_insert(self, df):
        """Ellenőrzi az UMS adatok érvényességét DB-mentés előtt.

        Ellenőrzések:
          1. Legalább 38 oszlop megléte
          2. Minden oszlop str típusú értékeket tartalmaz
          3. Kötelező mezők (Column1-3: szöveg, Column4+14: dátum, Column11: szám)
             nem lehetnek üresek és megfelelő formátumúak
        """
        if df.empty:
            QMessageBox.warning(self, "Hiba", "Nincs adat a mentéshez.")
            return False

        if df.shape[1] < 38:
            QMessageBox.warning(
                self, "Hiba", "Az adatok kevesebb mint 38 oszlopot tartalmaznak."
            )
            return False

        # Típus ellenőrzés: minden értéknek string-nek kell lennie
        for col_name in df.columns:
            if not df[col_name].dropna().map(lambda x: isinstance(x, str)).all():
                QMessageBox.warning(
                    self,
                    "Hiba",
                    f"A(z) {col_name} oszlopban nem minden érték szöveg (str) típusú.",
                )
                return False

        # Kötelező mezők definíciója: oszlopnév → elvárt értéktípus
        required_fields = {
            "Column1": "üres",
            "Column2": "üres",
            "Column3": "üres",
            "Column4": "dátum (yyyy.mm.dd)",
            "Column11": "decimális szám",
            "Column14": "dátum (yyyy.mm.dd)",
        }

        for col_name, check_type in required_fields.items():
            if col_name not in df.columns:
                QMessageBox.warning(self, "Hiba", f"Hiányzó oszlop: {col_name}")
                return False

            series = df[col_name]

            # Üresség ellenőrzés (None vagy üres string)
            if series.isnull().any() or (series.str.strip() == "").any():
                QMessageBox.warning(
                    self, "Hiba", f"A(z) {col_name} mező nem lehet üres."
                )
                return False

            if check_type == "dátum (yyyy.mm.dd)":
                try:
                    pd.to_datetime(series, format="%Y.%m.%d", errors="raise")
                except Exception:
                    QMessageBox.warning(
                        self,
                        "Hiba",
                        f"A(z) {col_name} oszlop nem érvényes dátumformátum: yyyy.mm.dd.",
                    )
                    return False

            elif check_type == "decimális szám":
                try:
                    series.str.replace(",", ".").astype(float)
                except Exception:
                    QMessageBox.warning(
                        self,
                        "Hiba",
                        f"A(z) {col_name} mező nem érvényes decimális szám.",
                    )
                    return False

        return True

    def run_database_save(self, df):
        """Elvégzi a tömeges adatbázis-mentést a Bank_stage táblába."""
        success, message = self.db.insert_bank_rows_bulk(df)
        self.hide_progress()

        if success:
            self.clear_data()   # sikeres mentés után az UI visszaáll alapállapotba
            QMessageBox.information(self, "Siker", message)
        else:
            QMessageBox.critical(self, "Hiba", message)

    # -------------------------------------------------------------------------
    # clear_data override (extra állapot törlése)
    # -------------------------------------------------------------------------

    def clear_data(self):
        """Az alap törlés mellett törli a betöltött fájlok halmazát és a DataFrame-et."""
        super().clear_data()
        self.loaded_files.clear()
        self.df_all = pd.DataFrame()

    # -------------------------------------------------------------------------
    # Banki segédmetódusok
    # -------------------------------------------------------------------------

    @staticmethod
    def fix_short_date(date_str):
        """Rövid éves dátumformátumot (dd.mm.yy) 4 jegyű éves formátumra (yyyy.mm.dd) alakít.

        A bank néha 2 jegyű évszámot exportál (pl. "01.03.24" → "2024.03.01").
        Ha a konverzió nem sikerül (pl. már helyes formátum), visszaadja az eredetit.
        """
        try:
            cleaned = str(date_str).strip()
            from datetime import datetime

            parsed = datetime.strptime(cleaned, "%d.%m.%y")
            return parsed.strftime("%Y.%m.%d")
        except (ValueError, TypeError):
            return str(date_str)

    def export_to_excel(self):
        """Kiválasztott oszlopok exportálása Excel fájlba (opcionális funkció).

        Az exportálható oszlopok: Column1_2 (kombinált), Column3, 4, 6, 7, 11, 14,
        17-21, 25, Column30_31 (kombinált), 32, 33.
        A fájlnév tartalmaz időbélyeget (pl. bank_export_2025-03-25_1430.xlsx).
        """
        if self.df_all.empty:
            QMessageBox.warning(self, "Hiba", "Nincs adat az exportáláshoz.")
            return

        df_to_export = self.df_all.copy()

        # Column1 + Column2 összefűzése "Column1_2" névvel (pl. azonosítókhoz)
        if "Column1" in df_to_export.columns and "Column2" in df_to_export.columns:
            df_to_export["Column1_2"] = (
                df_to_export["Column1"].fillna("")
                + "-"
                + df_to_export["Column2"].fillna("")
            )

        # Column30 + Column31 összefűzése "Column30_31" névvel (szállítónév)
        if "Column30" in df_to_export.columns and "Column31" in df_to_export.columns:
            df_to_export["Column30_31"] = (
                df_to_export["Column30"].fillna("")
                + ""
                + df_to_export["Column31"].fillna("")
            )

        # Csak a releváns oszlopok kerülnek az exportba
        export_columns = [
            "Column1_2", "Column3", "Column4", "Column6", "Column7",
            "Column11", "Column14", "Column17", "Column18", "Column19",
            "Column20", "Column21", "Column25", "Column30_31", "Column32", "Column33",
        ]

        df_to_export = df_to_export[
            [col for col in export_columns if col in df_to_export.columns]
        ]

        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        default_filename = f"bank_export_{timestamp}.xlsx"

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Mentés Excel fájlba", default_filename, "Excel fájlok (*.xlsx)"
        )

        if not file_path:
            return

        if not file_path.endswith(".xlsx"):
            file_path += ".xlsx"

        try:
            df_to_export.to_excel(file_path, index=False)
            QMessageBox.information(
                self, "Siker", f"A fájl sikeresen elmentve:\n{file_path}"
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Hiba", f"Hiba történt az exportálás során:\n{str(e)}"
            )
