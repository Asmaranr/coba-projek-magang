import os
import re
import json
import csv
import io
import tempfile
from datetime import datetime
from decimal import Decimal
import pandas as pd
import mysql.connector

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_file,
    redirect,
    url_for
)

from importer import (
    analyze_files,
    upload_to_database
)


app = Flask(__name__)



BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024


# ============================================================
# KONFIGURASI DATABASE
# ============================================================

DB_CONFIG = {
    "host": os.getenv(
        "DB_HOST",
        "localhost"
    ),

    "port": int(
        os.getenv(
            "DB_PORT",
            "3306"
        )
    ),

    "user": os.getenv(
        "DB_USER",
        "root"
    ),

    "password": os.getenv(
        "DB_PASSWORD",
        ""
    ),

    "database": os.getenv(
        "DB_NAME",
        "SIAKOFF"
    ),

    "table": os.getenv(
        "DB_TABLE",
        "DATA_LAPORAN_PENDUDUK"
    )
}


# ============================================================
# PENYIMPANAN HASIL SEMENTARA
# ============================================================

LAST_RESULT = {
    "database_df": None,
    "files": []
}

KECAMATAN_NAME_MAP = {
    "01": "Tegalrejo",
    "1": "Tegalrejo",
    "02": "Jetis",
    "2": "Jetis",
    "03": "Gondokusuman",
    "3": "Gondokusuman",
    "04": "Danurejan",
    "4": "Danurejan",
    "05": "Gedongtengen",
    "5": "Gedongtengen",
    "06": "Ngampilan",
    "6": "Ngampilan",
    "07": "Wirobrajan",
    "7": "Wirobrajan",
    "08": "Mantrijeron",
    "8": "Mantrijeron",
    "09": "Kraton",
    "9": "Kraton",
    "10": "Gondomanan",
    "11": "Pakualaman",
    "12": "Mergangsan",
    "13": "Umbulharjo",
    "14": "Kotagede"
}

KELURAHAN_NAME_MAP = {
    "01": {"1001": "Kricak", "1002": "Karangwaru", "1003": "Tegalrejo", "1004": "Bener"},
    "1": {"1001": "Kricak", "1002": "Karangwaru", "1003": "Tegalrejo", "1004": "Bener"},
    "02": {"1001": "Bumijo", "1002": "Cokrodiningratan", "1003": "Gowongan"},
    "2": {"1001": "Bumijo", "1002": "Cokrodiningratan", "1003": "Gondomanan"},
    "03": {"1001": "Demangan", "1002": "Kotabaru", "1003": "Klitren", "1004": "Baciro", "1005": "Terban"},
    "3": {"1001": "Demangan", "1002": "Kotabaru", "1003": "Klitren", "1004": "Baciro", "1005": "Terban"},
    "04": {"1001": "Suryatmajan", "1002": "Tegalpanggung", "1003": "Bausaran"},
    "4": {"1001": "Suryatmajan", "1002": "Tegalpanggung", "1003": "Bausaran"},
    "05": {"1001": "Sosromenduran", "1002": "Pringgokusuman"},
    "5": {"1001": "Sosromenduran", "1002": "Pringgokusuman"},
    "06": {"1001": "Ngampilan", "1002": "Notoprajan"},
    "6": {"1001": "Ngampilan", "1002": "Notoprajan"},
    "07": {"1001": "Pakuncen", "1002": "Wirobajan", "1003": "Patangpuluhan"},
    "7": {"1001": "Pakuncen", "1002": "Wirobajan", "1003": "Patangpuluhan"},
    "08": {"1001": "Gedongkiwo", "1002": "Suryodiningratan", "1003": "Mantrijeron"},
    "8": {"1001": "Gedongkiwo", "1002": "Suryodiningratan", "1003": "Mantrijeron"},
    "09": {"1001": "Patehan", "1002": "Panembahan", "1003": "Kadipaten"},
    "9": {"1001": "Pztehan", "1002": "Panembahan", "1003": "Kadipaten"},
    "10": {"1001": "Ngupasan", "1002": "Prawirodirjan"},
    "11": {"1001": "Purwokinanti", "1002": "Gunungketur"},
    "12": {"1001": "Keparakan", "1002": "Wirogunan", "1003": "Brontokusuman"},
    "13": {"1001": "Semaki", "1002": "Muja Muju", "1003": "Tahunan", "1004": "Warungboto", "1005": "Pandeyan", "1006": "Sorosutan", "1007": "Giwangan"},
    "14": {"1001": "Rejowinangun", "1002": "Prenggan", "1003": "Purbayan"}
}


def normalize_code(value):
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if text.isdigit():
        return str(int(text))
    return text


def _format_kecamatan_label(code):
    code = str(code).strip()
    if not code:
        return "- Semua kecamatan -"
    normalized_code = normalize_code(code)
    display_code = normalized_code if normalized_code else code
    name = KECAMATAN_NAME_MAP.get(normalized_code, KECAMATAN_NAME_MAP.get(f"{int(normalized_code):02d}", ""))
    return f"{name} ({display_code})" if name else code


def _format_kelurahan_label(kecamatan_code, kelurahan_code):
    kecamatan_code = normalize_code(kecamatan_code)
    kelurahan_code = normalize_code(kelurahan_code)
    if not kelurahan_code:
        return "- Semua kelurahan -"
    name = KELURAHAN_NAME_MAP.get(kecamatan_code, {}).get(kelurahan_code, "")
    if not name:
        padded_kecamatan = f"{int(kecamatan_code):02d}" if kecamatan_code.isdigit() else kecamatan_code
        name = KELURAHAN_NAME_MAP.get(padded_kecamatan, {}).get(kelurahan_code, "")
    return f"{name} ({kelurahan_code})" if name else kelurahan_code


def get_mysql_connection():
    return mysql.connector.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
        autocommit=True
    )


# ============================================================
# KONVERSI DATAFRAME -> JSON
# ============================================================

def dataframe_to_json_records(df):

    if df is None:
        return []

    if df.empty:
        return []

    records = df.astype(object).where(pd.notna(df), None).to_dict(orient="records")

    for record in records:
        for column, value in record.items():
            if isinstance(value, Decimal):
                record[column] = format(value, "f").replace(".", ",")

    return records


def dataframe_to_preview(df, limit=50):
    if df is None or df.empty:
        return df

    if "DESCRIP" not in df.columns:
        return df.head(limit)


    preview = (
        df.groupby("DESCRIP", sort=False, dropna=False)
        .head(10)
        .head(limit)
    )

    return preview


def _clean_cell(value):
    if value is None:
        return ""
    return str(value).strip().strip('"').strip("'")


def normalize_descrip_name(value):
    raw = _clean_cell(value)
    raw = re.sub(r"\s*\(DKB\)\s*$", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*\(.*?\)\s*$", "", raw)
    return raw.strip()


def load_section_descrip_master():
    json_candidate = os.path.join(BASE_DIR, "section_descrip_template.json")
    if os.path.exists(json_candidate):
        try:
            with open(json_candidate, "r", encoding="utf-8") as handle:
                data = json.load(handle)

            source = data.get("fungsi") if isinstance(data, dict) and isinstance(data.get("fungsi"), list) else data
            if isinstance(source, list):
                result = []
                seen = set()
                for item in source:
                    if not isinstance(item, dict):
                        continue
                    section = _clean_cell(item.get("section") or item.get("sect") or item.get("kode") or item.get("code"))
                    descrip = _clean_cell(item.get("descrip") or item.get("describ") or item.get("deskripsi") or item.get("name"))
                    if not section or not descrip:
                        continue
                    label = _clean_cell(item.get("label") or descrip)
                    status = _clean_cell(item.get("status") or "aktif")
                    key = (section, descrip)
                    if key in seen:
                        continue
                    seen.add(key)
                    result.append({
                        "section": section,
                        "descrip": descrip,
                        "slug": _clean_cell(item.get("slug") or section.lower()),
                        "label": label,
                        "status": status
                    })
                if result:
                    return result
        except Exception:
            pass

    candidates = [
        os.path.join(BASE_DIR, "section_descrip_template.csv"),
        os.path.join(BASE_DIR, "section_describ.csv"),
        os.path.join(BASE_DIR, "section_descrip.csv"),
        os.path.join(BASE_DIR, "section_describe.csv")
    ]

    for path in candidates:
        if not os.path.exists(path):
            continue

        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as handle:
                content = handle.read()
        except Exception:
            continue

        if not content.strip():
            continue

        try:
            dialect = csv.Sniffer().sniff(content[:4096], delimiters=",;\t|")
            reader = csv.reader(io.StringIO(content), dialect)
        except csv.Error:
            reader = csv.reader(io.StringIO(content), delimiter=",")

        rows = []
        for row in reader:
            cleaned = [_clean_cell(item) for item in row]
            if cleaned and any(cleaned):
                rows.append(cleaned)

        if not rows:
            continue

        header = []
        if rows and len(rows[0]) > 0:
            header = [str(item).strip().lower().replace(" ", "") for item in rows[0]]

        data_rows = rows[1:] if any(
            name in header for name in ["section", "sect", "kode", "code", "descrip", "describ", "deskripsi"]
        ) else rows

        result = []
        seen = set()

        for row in data_rows:
            if not row or not any(_clean_cell(cell) for cell in row):
                continue

            if len(row) >= 2:
                first = _clean_cell(row[0])
                second = _clean_cell(row[1])
            else:
                continue

            if not first or not second:
                continue

            section = ""
            if len(row) >= 3:
                third = _clean_cell(row[2])
                if third.lower() in {"pelayanan", "dkb"}:
                    section = third
                elif first.lower() in {"pelayanan", "dkb"}:
                    section = first
                elif second.lower() in {"pelayanan", "dkb"}:
                    section = second
                else:
                    section = first if first and not first.isdigit() else third or first

            if not section:
                section = first

            descrip = second
            label = second
            status = "aktif"

            if len(row) >= 3:
                third = _clean_cell(row[2])
                if third:
                    status = third
                    if third.lower() in {"pelayanan", "dkb"}:
                        if third.lower() == "dkb" and "(DKB)" not in descrip.upper():
                            descrip = f"{descrip} (DKB)"
                            label = f"{label} (DKB)"
                        status = "aktif"

            if len(row) >= 4:
                fourth = _clean_cell(row[3])
                if fourth and fourth.lower() not in {"pelayanan", "dkb"}:
                    label = fourth

            key = (section, descrip)
            if key in seen:
                continue
            seen.add(key)

            result.append({
                "section": section,
                "descrip": descrip,
                "slug": section.lower(),
                "label": label,
                "status": status
            })

        if result:
            return result

    return []


# ============================================================
# HALAMAN UTAMA
# ============================================================

@app.route("/")
def index():
    # Beranda publik (sebelum login)
    return render_template("beranda.html")


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "GET":
        return render_template("login.html")

    username = request.form.get("username", "")
    password = request.form.get("password", "")

    if username == "admin" and password == "admin123":
        return redirect(url_for("home"))

    return render_template(
        "login.html",
        error="Username atau password salah."
    ), 401


@app.route("/logout")
def logout():
    return redirect(url_for("index"))


@app.route("/home")
def home():
    return render_template("home.html")


@app.route("/import")
def import_page():
    return render_template("index.html")


@app.route("/upload")
def upload_page():
    return render_template("upload_dkb.html")


@app.route("/penyajian")
def penyajian_page():
    return render_template("penyajian_dkb.html")


@app.route("/penyajian_guest")
def penyajian_guest_page():
    return render_template("penyajian_guest.html")


@app.route("/penyajian_dkb.html")
def penyajian_dkb_page():
    return render_template("penyajian_dkb.html")


@app.get("/api/master/section-descrip")
def section_descrip_master_api():
    return jsonify({
        "success": True,
        "data": load_section_descrip_master()
    })


@app.get("/api/penyajian/filter-options")
def penyajian_filter_options():
    table = DB_CONFIG["table"]
    response = {
        "tanggal": [],
        "fungsi": [],
        "kecamatan": [],
        "kelurahan": [],
        "sect": []
    }

    master_items = load_section_descrip_master()
    if master_items:
        seen_fungsi = set()
        seen_sect = set()
        ordered_fungsi = []
        ordered_sect = []

        for item in master_items:
            name = _clean_cell(item.get("descrip"))
            section = _clean_cell(item.get("section") or item.get("sect") or item.get("section_name") or item.get("kode") or item.get("code"))
            normalized_name = normalize_descrip_name(name)
            label = name or _clean_cell(item.get("label") or normalized_name)

            fung_key = (section.lower(), normalized_name.lower()) if section and normalized_name else ("", normalized_name.lower() if normalized_name else "")
            if normalized_name and fung_key not in seen_fungsi:
                seen_fungsi.add(fung_key)
                ordered_fungsi.append({
                    "value": normalized_name,
                    "label": normalized_name,
                    "section": section,
                    "sect": section
                })

            if section and section not in seen_sect:
                seen_sect.add(section)
                ordered_sect.append({"value": section, "label": section})

        response["fungsi"] = ordered_fungsi
        response["sect"] = ordered_sect

    try:
        connection = get_mysql_connection()
        cursor = connection.cursor(dictionary=True)

        queries = {
            "tanggal": (
                f"SELECT DISTINCT TANGGAL AS value FROM `{table}` "
                "WHERE TANGGAL IS NOT NULL AND TANGGAL <> '' "
                "ORDER BY TANGGAL DESC"
            ),
            "kecamatan": (
                f"SELECT DISTINCT NO_KEC AS value FROM `{table}` "
                "WHERE NO_KEC IS NOT NULL AND NO_KEC <> '' "
                "AND CHAR_LENGTH(NO_KEC) <= 2 "
                "ORDER BY CAST(NO_KEC AS UNSIGNED) ASC"
            ),
            "kelurahan": (
                f"SELECT DISTINCT NO_KEC AS kecamatan, NO_KEL AS value FROM `{table}` "
                "WHERE NO_KEL IS NOT NULL AND NO_KEL <> '' "
                "ORDER BY CAST(NO_KEC AS UNSIGNED), CAST(NO_KEL AS UNSIGNED)"
            )
        }

        for key, sql in queries.items():
            cursor.execute(sql)
            response[key] = cursor.fetchall()

        clean_tanggal = []
        for row in response["tanggal"]:
            value = row.get("value") if isinstance(row, dict) else row
            if value is None:
                continue
            value = str(value).strip()
            if value:
                clean_tanggal.append({"value": value, "label": value})
        response["tanggal"] = clean_tanggal

        clean_kecamatan = []
        for row in response["kecamatan"]:
            value = row.get("value") if isinstance(row, dict) else row
            if value is None:
                continue
            value = str(value).strip()
            if value:
                clean_kecamatan.append({
                    "value": value,
                    "label": _format_kecamatan_label(value)
                })
        response["kecamatan"] = clean_kecamatan

        clean_kelurahan = []
        for row in response["kelurahan"]:
            kecamatan = row.get("kecamatan")
            value = row.get("value")
            if value is None:
                continue
            value = str(value).strip()
            if not value:
                continue
            clean_kelurahan.append({
                "value": value,
                "label": _format_kelurahan_label(kecamatan, value),
                "kecamatan": str(kecamatan) if kecamatan is not None else ""
            })
        response["kelurahan"] = clean_kelurahan

        response["tanggal"] = [
            {"value": item["value"], "label": item["value"]}
            for item in response["tanggal"]
        ]

        return jsonify({
            "success": True,
            "data": response
        })

    except Exception as exc:
        print("ERROR FILTER OPTIONS", exc)
        return jsonify({
            "success": False,
            "message": str(exc)
        }), 500

    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            connection.close()
        except Exception:
            pass


@app.get("/api/penyajian/data")
def penyajian_data():
    table = DB_CONFIG["table"]
    filters = {
        "tanggal": request.args.get("tanggal", "").strip(),
        "descrip": request.args.get("descrip", "").strip(),
        "no_kec": request.args.get("no_kec", "").strip(),
        "no_kel": request.args.get("no_kel", "").strip(),
        "sect": request.args.get("sect", "").strip()
    }

    query = (
        f"SELECT TANGGAL, NO_PROP, NO_KAB, NO_KEC, NO_KEL, LAKI_LAKI, "
        f"PEREMPUAN, JUMLAH, NO, DESCRIP, SECT FROM `{table}` WHERE 1=1"
    )
    params = []

    if filters["tanggal"]:
        query += " AND TANGGAL = %s"
        params.append(filters["tanggal"])

    if filters["sect"]:
        query += " AND LOWER(TRIM(SECT)) = LOWER(TRIM(%s))"
        params.append(filters["sect"])
    elif filters["descrip"]:
        normalized_descrip = normalize_descrip_name(filters["descrip"])
        query += " AND (LOWER(TRIM(DESCRIP)) = LOWER(TRIM(%s)) OR LOWER(TRIM(DESCRIP)) = LOWER(TRIM(%s)) OR LOWER(TRIM(REPLACE(DESCRIP, ' (DKB)', ''))) = LOWER(TRIM(%s)))"
        params.extend([
            filters["descrip"],
            f"{filters['descrip']} (DKB)",
            normalized_descrip
        ])

    if filters["no_kec"]:
        query += " AND NO_KEC = %s"
        params.append(filters["no_kec"])

    if filters["no_kel"]:
        query += " AND NO_KEL = %s"
        params.append(filters["no_kel"])

    query += " ORDER BY TANGGAL DESC, DESCRIP ASC, NO_KEC ASC, NO_KEL ASC"

    try:
        connection = get_mysql_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, params)
        rows = cursor.fetchall()

        return jsonify({
            "success": True,
            "rows": rows,
            "total": len(rows)
        })

    except Exception as exc:
        print("ERROR FILTERED DATA", exc)
        return jsonify({
            "success": False,
            "message": str(exc)
        }), 500

    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            connection.close()
        except Exception:
            pass


# ============================================================
# ANALISIS FILE EXCEL
# ============================================================

@app.post("/analyze")
def analyze():

    # --------------------------------------------------------
    # Ambil semua file dari form
    # --------------------------------------------------------

    files = request.files.getlist(
        "files"
    )

    # --------------------------------------------------------
    # Ambil SECT masing-masing file
    # --------------------------------------------------------

    sect_values = request.form.getlist(
        "sect"
    )

    # --------------------------------------------------------
    # Ambil TANGGAL masing-masing file
    # --------------------------------------------------------

    tanggal_values = request.form.getlist(
        "tanggal"
    )

    # --------------------------------------------------------
    # Ambil NO masing-masing file
    # --------------------------------------------------------

    nomor_values = request.form.getlist(
        "nomor"
    )

    # --------------------------------------------------------
    # Penyimpanan file sementara
    # --------------------------------------------------------

    valid_files = []
    temp_paths = []

    # --------------------------------------------------------
    # Validasi
    # --------------------------------------------------------

    if not files:

        return jsonify({
            "success": False,
            "message": "Pilih minimal satu file Excel."
        }), 400

    try:

        # ====================================================
        # PROSES SETIAP FILE
        # ====================================================

        for index, file in enumerate(files):

            # ------------------------------------------------
            # File kosong
            # ------------------------------------------------

            if not file:
                continue

            if not file.filename:
                continue

            filename = file.filename

            # ------------------------------------------------
            # Validasi ekstensi
            # ------------------------------------------------

            if not filename.lower().endswith(
                (
                    ".xlsx",
                    ".xls"
                )
            ):

                return jsonify({
                    "success": False,
                    "message":
                        f"File '{filename}' "
                        "bukan file Excel. "
                        "Gunakan .xlsx atau .xls."
                }), 400

            # ------------------------------------------------
            # Ambil ekstensi
            # ------------------------------------------------

            suffix = os.path.splitext(
                filename
            )[1]

            # ------------------------------------------------
            # Buat file temporary
            # ------------------------------------------------

            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=suffix
            ) as tmp:

                file.save(
                    tmp.name
                )

                temp_paths.append(
                    tmp.name
                )

                # --------------------------------------------
                # Ambil SECT
                # --------------------------------------------

                sect = ""

                if index < len(
                    sect_values
                ):

                    sect = (
                        sect_values[index]
                        .strip()
                    )

                # --------------------------------------------
                # Ambil TANGGAL manual
                # --------------------------------------------

                tanggal = ""

                if index < len(
                    tanggal_values
                ):

                    tanggal = (
                        tanggal_values[index]
                        .strip()
                    )

                if tanggal:

                    try:

                        datetime.strptime(
                            tanggal,
                            "%Y-%m-%d"
                        )

                    except ValueError:

                        return jsonify({
                            "success": False,
                            "message":
                                f"Tanggal untuk file '{filename}' "
                                "harus berformat YYYY-MM-DD."
                        }), 400

                nomor = ""

                if index < len(
                    nomor_values
                ):

                    nomor = (
                        nomor_values[index]
                        .strip()
                    )

                # --------------------------------------------
                # Masukkan file ke daftar
                # --------------------------------------------

                valid_files.append({

                    "path":
                        tmp.name,

                    "filename":
                        filename,

                    "sect":
                        sect or None,

                    "tanggal":
                        tanggal or None,

                    "nomor":
                        nomor or None
                })

        # ====================================================
        # CEK FILE VALID
        # ====================================================

        if not valid_files:

            return jsonify({
                "success": False,
                "message":
                    "Tidak ada file Excel yang valid."
            }), 400

        # ====================================================
        # ANALISIS SEMUA FILE
        # ====================================================

        result = analyze_files(
            valid_files
        )

        # ====================================================
        # SIMPAN HASIL
        # ====================================================

        LAST_RESULT[
            "database_df"
        ] = result[
            "database_df"
        ]

        LAST_RESULT[
            "files"
        ] = result[
            "files"
        ]

        # ====================================================
        # PREVIEW
        # ====================================================
        #
        # Hanya 50 baris pertama yang dikirim ke UI.
        #
        # NaN otomatis menjadi null.
        # ====================================================

        preview_df = dataframe_to_preview(
            result["database_df"]
        )

        preview = (
            dataframe_to_json_records(
                preview_df
            )
        )

        # ====================================================
        # INFORMASI FILE
        # ====================================================

        response_files = []

        for item in result[
            "files"
        ]:

            # ------------------------------------------------
            # Group DESCRIP
            # ------------------------------------------------

            groups = []

            for descrip, group in item[
                "groups"
            ].items():

                groups.append({

                    "descrip":
                        str(descrip),

                    "male":
                        group[
                            "male"
                        ],

                    "female":
                        group[
                            "female"
                        ],

                    "total":
                        group[
                            "total"
                        ]
                })

            # ------------------------------------------------
            # Data file
            # ------------------------------------------------

            response_files.append({

                "filename":
                    item[
                        "filename"
                    ],

                "success":
                    item[
                        "success"
                    ],

                "message":
                    item[
                        "message"
                    ],

                "rows":
                    item[
                        "rows"
                    ],

                "columns":
                    item[
                        "columns"
                    ],

                "region_column":
                    item[
                        "region_column"
                    ],

                "groups":
                    groups,

                "detected":
                    item[
                        "detected"
                    ],

                "database_rows":
                    item[
                        "database_rows"
                    ],

                "sect":
                    item[
                        "sect"
                    ] or "",

                "tanggal":
                    item[
                        "tanggal"
                    ] or "",

                "nomor":
                    item[
                        "nomor"
                    ] or ""
            })

        # ====================================================
        # RESPONSE KE UI
        # ====================================================

        return jsonify({

            "success":
                True,

            "total_files":
                result[
                    "total_files"
                ],

            "success_files":
                result[
                    "success_files"
                ],

            "failed_files":
                result[
                    "failed_files"
                ],

            "database_rows":
                result[
                    "database_rows"
                ],

            "files":
                response_files,

            "preview":
                preview
        })

    # ========================================================
    # ERROR
    # ========================================================

    except Exception as e:

        print()
        print("=" * 80)
        print("ERROR ANALISIS")
        print("=" * 80)
        print(
            type(e).__name__,
            "errno=", getattr(e, "errno", None),
            "sqlstate=", getattr(e, "sqlstate", None),
            str(e)
        )

        return jsonify({

            "success":
                False,

            "message":
                str(e)

        }), 500

    # ========================================================
    # HAPUS FILE TEMPORARY
    # ========================================================

    finally:

        for path in temp_paths:

            try:

                if os.path.exists(
                    path
                ):

                    os.remove(
                        path
                    )

            except Exception:

                pass


# ============================================================
# UPLOAD KE DATABASE
# ============================================================

@app.post("/upload-db")
def upload_db():

    # --------------------------------------------------------
    # Ambil hasil analisis
    # --------------------------------------------------------

    database_df = LAST_RESULT.get(
        "database_df"
    )

    # --------------------------------------------------------
    # Validasi
    # --------------------------------------------------------

    if (
        database_df is None
        or database_df.empty
    ):

        return jsonify({

            "success":
                False,

            "message":
                "Belum ada hasil mapping. "
                "Silakan analisis file Excel terlebih dahulu."

        }), 400

    # --------------------------------------------------------
    # Upload
    # --------------------------------------------------------

    try:

        count = upload_to_database(
            database_df,
            DB_CONFIG
        )

        return jsonify({

            "success":
                True,

            "message":
                f"{count} baris berhasil "
                "dimasukkan ke database.",

            "count":
                count

        })

    except Exception as e:

        print()
        print("=" * 80)
        print("ERROR UPLOAD DATABASE")
        print("=" * 80)
        print(e)

        return jsonify({

            "success":
                False,

            "message":
                str(e)

        }), 500


# ============================================================
# EXPORT HASIL MAPPING
# ============================================================

@app.get("/export")
def export():

    # --------------------------------------------------------
    # Ambil DataFrame
    # --------------------------------------------------------

    database_df = LAST_RESULT.get(
        "database_df"
    )

    # --------------------------------------------------------
    # Validasi
    # --------------------------------------------------------

    if (
        database_df is None
        or database_df.empty
    ):

        return (
            "Belum ada hasil mapping.",
            400
        )

    # --------------------------------------------------------
    # File temporary
    # --------------------------------------------------------

    output = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".xlsx"
    )

    output.close()

    try:

        # ----------------------------------------------------
        # Simpan Excel
        # ----------------------------------------------------

        database_df.to_excel(
            output.name,
            index=False
        )

        # ----------------------------------------------------
        # Kirim ke browser
        # ----------------------------------------------------

        return send_file(

            output.name,

            as_attachment=True,

            download_name=
                "hasil_mapping_semua_file.xlsx",

            mimetype=
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        )

    except Exception as e:

        if os.path.exists(
            output.name
        ):

            os.remove(
                output.name
            )

        return (
            str(e),
            500
        )


# ============================================================
# HEALTH CHECK
# ============================================================
#
# Digunakan untuk memastikan Flask hidup.
# ============================================================

@app.get("/health")
def health():

    return jsonify({

        "success":
            True,

        "message":
            "SIAKOFF Import System berjalan.",

        "database":
            DB_CONFIG[
                "database"
            ],

        "table":
            DB_CONFIG[
                "table"
            ]

    })


# ============================================================
# ERROR HANDLER
# ============================================================

@app.errorhandler(
    413
)
def request_entity_too_large(error):

    return jsonify({

        "success":
            False,

        "message":
            "Ukuran file terlalu besar. "
            "Maksimal total upload adalah 200 MB."

    }), 413


# ============================================================
# PROGRAM UTAMA
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 80)
    print("SIAKOFF - SISTEM IMPORT BANYAK EXCEL")
    print("=" * 80)

    print()
    print(
        "Server berjalan di:"
    )

    print(
        "http://127.0.0.1:5000"
    )

    print()
    print(
        f"Database : "
        f"{DB_CONFIG['database']}"
    )

    print(
        f"Tabel    : "
        f"{DB_CONFIG['table']}"
    )

    print()
    print("=" * 80)

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )