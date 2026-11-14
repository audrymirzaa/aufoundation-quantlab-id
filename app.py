from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from engine import assistant, benchmarks, csv_io, universe
from engine.data import (
    align_series,
    detect_frequency,
    fetch_prices,
    periodic_returns,
)
from engine.formats import PERIOD_LABEL, normalize_period
from engine.fundamentals import fetch_fundamentals
from engine.metrics import analyze_universe
from engine.ui_data import (
    FIELD_LABELS,
    FIELD_ORDER,
    allowed_periods,
    build_display_frame,
    correlation_table,
    dataset_code_from_filename,
    frames_to_excel,
    medians_display,
    merge_datasets,
    metrics_table,
    quadrant_display,
    resample_price_frame,
    risk_table,
    source_note,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
FUNDAMENTALS_PATH = DATA_DIR / "fundamentals.csv"
SECTOR_MAP_PATH = DATA_DIR / "sector_map.csv"
MAX_FETCH = 60


def fundamental_sector_lookup() -> dict[str, str]:
    lookup = benchmarks.load_sector_map(SECTOR_MAP_PATH)
    lookup.update(universe.sector_lookup())
    return lookup


def fetch_fundamentals_for(
    codes: list[str],
    *,
    overwrite: bool = False,
    label: str = "Mengambil fundamental",
):
    clean = []
    for code in codes:
        text = universe.normalize_code(code)
        if text and text not in clean:
            clean.append(text)
    if not clean:
        return None
    lookup = fundamental_sector_lookup()
    sector_lookup = {code: lookup.get(code, "Lainnya") for code in clean}
    progress = st.progress(0.0, text=label)

    def update(done: int, total: int, code: str) -> None:
        progress.progress(done / total, text=f"{label} {done}/{total}: {code}")

    try:
        incoming, warnings = fetch_fundamentals(
            clean,
            sector_lookup=sector_lookup,
            progress=update,
        )
        st.session_state.fundamentals = benchmarks.merge_fundamentals(
            st.session_state.get("fundamentals"),
            incoming,
            overwrite=overwrite,
        )
        st.session_state["fundamental_warnings"] = warnings
        return incoming
    finally:
        progress.empty()


try:
    from st_aggrid import AgGrid, GridOptionsBuilder, JsCode
    HAS_AGGGRID = True
except Exception:
    HAS_AGGGRID = False

st.set_page_config(page_title="QuantLab", page_icon=None, layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Playfair+Display:wght@600&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1550px; }
    h1 { font-family: 'Playfair Display', Georgia, serif; font-weight: 600; letter-spacing: -0.01em; }
    h2, h3 { font-family: 'Inter', sans-serif; letter-spacing: -0.01em; }
    [data-testid="stMetricValue"] { font-variant-numeric: tabular-nums; }
    [data-testid="stDataFrame"] { font-variant-numeric: tabular-nums; }
    .ql-note { color: #475467; font-size: 0.88rem; line-height: 1.5; }
    .ql-badge { display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: 0.75rem; font-weight: 600; }
    .ql-badge-ok { background: #ecfdf3; color: #067647; }
    .ql-badge-warn { background: #fef3f2; color: #b42318; }
    .ql-badge-neutral { background: #f2f4f7; color: #344054; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def parse_upload(filename: str, data: bytes) -> csv_io.ParsedCsv:
    return csv_io.read_csv(data)


def init_state() -> None:
    defaults = {
        "datasets": {},
        "market": None,
        "upload_signature": None,
        "fundamentals": None,
        "assistant_messages": [],
        "assistant_suggestions": [],
        "assistant_candidates": [],
        "assistant_query": "",
        "assistant_prompt": "",
        "assistant_mode": "API lokal (OpenAI-compatible)",
        "assistant_endpoint": "http://127.0.0.1:11434/v1",
        "assistant_model": "qwen2.5:3b",
        "assistant_key": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def build_mapping(
    parsed: csv_io.ParsedCsv,
    code: str,
    date_column: str,
    price_column: str,
    change_column: str | None,
) -> csv_io.Mapping:
    suggested = csv_io.suggest_mapping(parsed)
    specs = [
        csv_io.ColumnSpec(source=date_column, target="date", kind="date"),
        csv_io.ColumnSpec(source=price_column, target=code, kind="price"),
    ]
    if change_column:
        specs.append(
            csv_io.ColumnSpec(
                source=change_column,
                target=f"{code}_change",
                kind="change_percent",
                percent=True,
            )
        )
    for role in ("open", "high", "low"):
        source = suggested.get(f"{role}_column")
        if source and source not in (date_column, price_column, change_column):
            specs.append(csv_io.ColumnSpec(source=source, target=f"{code}_{role}", kind=role))
    volume_source = suggested.get("volume_column")
    if volume_source and volume_source not in (date_column, price_column, change_column):
        specs.append(csv_io.ColumnSpec(source=volume_source, target=f"{code}_volume", kind="volume"))
    return csv_io.Mapping(
        instrument=code,
        columns=specs,
        date_format=parsed.detection.date_format,
    )


def compute_returns(
    datasets: dict[str, dict],
    target_period: str,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], dict[str, bool]]:
    frames: dict[str, pd.Series] = {}
    display: dict[str, pd.DataFrame] = {}
    labels: dict[str, bool] = {}
    target = normalize_period(target_period)
    for code, dataset in datasets.items():
        frame = dataset["frame"]
        source = normalize_period(dataset["source_period"])
        resampled = resample_price_frame(frame, target)
        display[code] = resampled
        change_column = f"{code}_change"
        if target == source and dataset["mode"] == "change" and change_column in frame.columns:
            series = frame[change_column]
            labels[code] = True
        else:
            series = periodic_returns(frame[[code]], target).iloc[:, 0]
            labels[code] = bool(dataset.get("label_change", False))
        frames[code] = series
    returns = align_series(frames)
    return returns, display, labels


def render_grid(
    display: pd.DataFrame,
    percent_columns: list[str],
    volume_columns: list[str],
    locale: str,
    decimals: int,
) -> None:
    js_locale = "id-ID" if locale == "id" else "en-US"
    if not HAS_AGGGRID:
        st.dataframe(display, width="stretch", hide_index=True)
        return
    builder = GridOptionsBuilder.from_dataframe(display)
    builder.configure_default_column(sortable=True, filter=True, resizable=True, editable=False)
    number_formatter = JsCode(
        "function(params){if(params.value===null||params.value===undefined)return '';"
        f"return Number(params.value).toLocaleString('{js_locale}',"
        f"{{minimumFractionDigits:{decimals},maximumFractionDigits:{decimals}}});}}"
    )
    percent_formatter = JsCode(
        "function(params){if(params.value===null||params.value===undefined)return '';"
        f"var v=Number(params.value)*100;return v.toLocaleString('{js_locale}',"
        f"{{minimumFractionDigits:{decimals},maximumFractionDigits:{decimals}}})+'%';}}"
    )
    volume_formatter = JsCode(
        "function(params){if(params.value===null||params.value===undefined)return '';"
        f"return Number(params.value).toLocaleString('{js_locale}',{{maximumFractionDigits:0}});}}"
    )
    percent_style = JsCode(
        "function(params){if(params.value===null||params.value===undefined)return {};"
        "return {color: params.value < 0 ? '#b42318' : '#067647', fontWeight: 500, textAlign: 'right'};}"
    )
    date_formatter = JsCode(
        "function(params){if(!params.value)return '';var d=new Date(params.value);"
        "return d.toISOString().slice(0,10);}"
    )
    for column in display.columns:
        if column == "Tanggal":
            builder.configure_column(column, pinned="left", width=118, filter="agDateColumnFilter", valueFormatter=date_formatter)
        elif column in percent_columns:
            builder.configure_column(
                column,
                type=["numericColumn"],
                filter="agNumberColumnFilter",
                valueFormatter=percent_formatter,
                cellStyle=percent_style,
                width=132,
            )
        elif column in volume_columns:
            builder.configure_column(
                column,
                type=["numericColumn"],
                filter="agNumberColumnFilter",
                valueFormatter=volume_formatter,
                width=120,
            )
        else:
            builder.configure_column(
                column,
                type=["numericColumn"],
                filter="agNumberColumnFilter",
                valueFormatter=number_formatter,
                width=112,
            )
    pagination = len(display) > 60
    builder.configure_grid_options(
        domLayout="normal" if pagination else "autoHeight",
        suppressAggFuncInHeader=True,
        enableCellTextSelection=True,
        pagination=pagination,
        paginationPageSize=50,
    )
    height = 580 if pagination else min(680, 44 + len(display) * 32)
    AgGrid(
        display,
        gridOptions=builder.build(),
        allow_unsafe_jscode=True,
        height=height,
        fit_columns_on_grid_load=False,
        key="quantlab_grid",
    )


def correlation_style(value: float) -> str:
    if pd.isna(value):
        return ""
    intensity = min(abs(float(value)), 1.0)
    if value >= 0:
        return f"background-color: rgba(6, 118, 71, {0.12 + 0.38 * intensity}); color: #101828;"
    return f"background-color: rgba(180, 35, 24, {0.12 + 0.38 * intensity}); color: #101828;"


def quadrant_cell_style(value: object) -> str:
    if not isinstance(value, str):
        return ""
    if value.startswith("Kuadran 1"):
        return "background-color: #ecfdf3; color: #067647; font-weight: 600;"
    if value.startswith("Kuadran 2"):
        return "background-color: #fffaeb; color: #b54708; font-weight: 600;"
    if value.startswith("Kuadran 3"):
        return "background-color: #eff8ff; color: #175cd3; font-weight: 600;"
    if value.startswith("Kuadran 4"):
        return "background-color: #fef3f2; color: #b42318; font-weight: 600;"
    return "background-color: #f2f4f7; color: #344054;"


def render_assistant(context: str) -> None:
    st.subheader("Asisten Qwen")
    stats = universe.stats()
    st.caption(
        "Tanya industri atau ticker. Sumber kandidat: data/ticker_universe.csv "
        f"({stats['count']} emiten; {stats['banks']} bank; {stats['plantation']} sawit/perkebunan). "
        "Qwen hanya memilih dari kandidat itu, lalu aplikasi menarik harganya dari yfinance."
    )
    fundamental_warnings = st.session_state.pop("fundamental_warnings", None)
    if fundamental_warnings:
        st.warning(
            "Sebagian fundamental tidak terambil: " + "; ".join(fundamental_warnings[:6])
        )
    with st.expander("Pengaturan Qwen", expanded=not st.session_state.assistant_messages):
        mode = st.radio(
            "Mode asisten",
            ["API lokal (OpenAI-compatible)", "Copy-paste prompt", "Katalog offline"],
            key="assistant_mode",
            horizontal=True,
        )
        endpoint = st.text_input("Endpoint", key="assistant_endpoint")
        model = st.text_input("Model", key="assistant_model")
        api_key = st.text_input("API key (opsional)", type="password", key="assistant_key")
        if st.button("Tes koneksi", key=f"assistant_test_{context}"):
            try:
                reply = assistant.test_connection(endpoint, model, api_key or None)
                st.success(f"Terhubung. Jawaban model: {reply[:80]}")
            except Exception as exc:
                st.error(str(exc))
        st.caption("Ollama: http://127.0.0.1:11434/v1. LM Studio: http://127.0.0.1:1234/v1.")

    for message in st.session_state.assistant_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    query = st.chat_input(
        "Contoh: carikan ticker saham semen dan bank",
        key=f"assistant_chat_{context}",
    )
    if query:
        st.session_state.assistant_messages.append({"role": "user", "content": query})
        candidates, broad = assistant.universe_suggestions(query)
        st.session_state.assistant_candidates = candidates
        st.session_state.assistant_query = query
        if not candidates:
            st.session_state.assistant_suggestions = []
            st.session_state.assistant_messages.append(
                {
                    "role": "assistant",
                    "content": (
                        "Tidak ada kandidat di ticker_universe.csv untuk pertanyaan itu. "
                        "Coba sebutkan sektor, subsektor, nama emiten, atau kode 4 huruf."
                    ),
                }
            )
        elif mode.startswith("API"):
            try:
                with st.spinner("Menghubungi Qwen..."):
                    reply = assistant.ask_openai(
                        endpoint,
                        model,
                        query,
                        candidates=candidates,
                        history=None,
                        api_key=api_key or None,
                    )
                parsed = assistant.parse_ticker_response(reply)
                candidate_codes = {item["code"] for item in candidates}
                qwen_chosen = [item for item in parsed["tickers"] if item["code"] in candidate_codes]
                suggestions, ignored = assistant.select_suggestions(query, parsed["tickers"], candidates)
                if broad:
                    content = f"Universe menemukan {len(candidates)} ticker. Qwen menyebut {len(qwen_chosen)}."
                    if parsed["message"]:
                        content = f"{content} {parsed['message']}"
                else:
                    content = parsed["message"] or f"Menemukan {len(suggestions)} ticker."
                st.session_state.assistant_messages.append({"role": "assistant", "content": content})
                st.session_state.assistant_suggestions = suggestions
                if ignored:
                    st.session_state.assistant_messages.append(
                        {
                            "role": "assistant",
                            "content": "Kode di luar universe/kandidat dibuang: " + ", ".join(ignored[:12]),
                        }
                    )
                if parsed["error"]:
                    st.session_state.assistant_messages.append(
                        {"role": "assistant", "content": f"Catatan parser: {parsed['error']}"}
                    )
            except Exception as exc:
                st.session_state.assistant_messages.append(
                    {"role": "assistant", "content": f"Gagal memanggil Qwen: {exc}"}
                )
                st.session_state.assistant_suggestions = candidates
        elif mode.startswith("Copy"):
            st.session_state.assistant_prompt = assistant.build_copy_prompt(query, candidates)
            st.session_state.assistant_suggestions = []
            st.session_state.assistant_messages.append(
                {"role": "assistant", "content": "Prompt siap. Salin ke Qwen, lalu tempel jawabannya di bawah."}
            )
        else:
            st.session_state.assistant_suggestions = candidates
            st.session_state.assistant_messages.append(
                {"role": "assistant", "content": f"Universe menemukan {len(candidates)} ticker."}
            )
        st.session_state.pop(f"assistant_selected_{context}", None)
        st.rerun()

    if mode.startswith("Copy") and st.session_state.assistant_prompt:
        st.code(st.session_state.assistant_prompt, language="text")
        pasted = st.text_area("Tempel jawaban JSON dari Qwen", key=f"assistant_paste_{context}", height=160)
        if st.button("Proses jawaban Qwen", key=f"assistant_process_{context}"):
            parsed = assistant.parse_ticker_response(pasted)
            candidates = st.session_state.assistant_candidates or assistant.universe_suggestions(
                st.session_state.assistant_query
            )[0]
            suggestions, ignored = assistant.select_suggestions(
                st.session_state.assistant_query, parsed["tickers"], candidates
            )
            st.session_state.assistant_suggestions = suggestions
            if ignored:
                st.session_state.assistant_messages.append(
                    {"role": "assistant", "content": "Kode di luar universe/kandidat dibuang: " + ", ".join(ignored[:12])}
                )
            if suggestions:
                content = parsed["message"] or f"Menemukan {len(suggestions)} ticker."
            else:
                content = parsed["error"] or "Tidak ada ticker yang bisa dibaca."
            st.session_state.assistant_messages.append({"role": "assistant", "content": content})
            st.session_state.pop(f"assistant_selected_{context}", None)
            st.rerun()

    suggestions = st.session_state.assistant_suggestions
    if suggestions:
        st.markdown("**Ticker yang disarankan**")
        st.dataframe(assistant.catalog_table(suggestions), width="stretch", hide_index=True)
        st.caption(
            f"Sumber: data/ticker_universe.csv — {len(suggestions)} kandidat. "
            f"Maksimal {MAX_FETCH} ticker diambil per percobaan."
        )
        if len(suggestions) > MAX_FETCH:
            st.warning(f"Kandidat lebih dari {MAX_FETCH}. Pilih subset atau persempit kata kunci.")
        labels = {
            f"{item['code']} — {item['name'] or 'tanpa nama'} ({item['sector'] or 'sektor belum diisi'}"
            f"{' / ' + item['subsector'] if item.get('subsector') else ''})": item["code"]
            for item in suggestions
        }
        selected_labels = st.multiselect(
            "Pilih ticker yang akan diambil",
            list(labels),
            default=list(labels),
            key=f"assistant_selected_{context}",
        )
        selected = [labels[label] for label in selected_labels]
        input_columns = st.columns(3)
        start = input_columns[0].date_input(
            "Mulai",
            value=pd.Timestamp("2024-01-01"),
            key=f"assistant_start_{context}",
        )
        end = input_columns[1].date_input(
            "Selesai",
            value=pd.Timestamp.today().normalize(),
            key=f"assistant_end_{context}",
        )
        benchmark = input_columns[2].text_input("Benchmark", value="^JKSE", key=f"assistant_bench_{context}")
        if st.button("Ambil data dari yfinance", type="primary", key=f"assistant_fetch_{context}"):
            if not selected:
                st.warning("Pilih minimal satu ticker.")
            elif pd.Timestamp(start) >= pd.Timestamp(end):
                st.error("Tanggal mulai harus lebih awal dari tanggal selesai.")
            elif len(selected) > MAX_FETCH:
                st.error(f"Maksimal {MAX_FETCH} ticker per percobaan. Pilih subset dulu.")
            else:
                benchmark_code = benchmark.strip().upper()
                symbols = list(dict.fromkeys(selected + [benchmark_code]))
                with st.spinner("Mengambil data dari yfinance..."):
                    try:
                        prices = fetch_prices(symbols, start=str(start), end=str(end))
                        new_datasets: dict[str, dict] = {}
                        for code in prices.columns:
                            frame = pd.DataFrame({code: prices[code]}).dropna()
                            if frame.empty:
                                continue
                            new_datasets[code] = {
                                "frame": frame,
                                "source_period": detect_frequency(frame.index),
                                "mode": "price",
                                "label_change": False,
                                "file": "yfinance",
                            }
                        if len(new_datasets) < 2:
                            st.error("Data tidak cukup. Cek kode ticker dan rentang tanggal.")
                        else:
                            merged = merge_datasets(st.session_state.datasets, new_datasets)
                            st.session_state.datasets = merged
                            if st.session_state.market not in merged:
                                st.session_state.market = (
                                    benchmark_code if benchmark_code in merged else next(iter(merged))
                                )
                            current_fundamentals = st.session_state.get("fundamentals")
                            sector_lookup = fundamental_sector_lookup()
                            today = pd.Timestamp.today().strftime("%Y-%m-%d")
                            if not isinstance(current_fundamentals, pd.DataFrame):
                                current_fundamentals = pd.DataFrame()
                            if current_fundamentals.empty:
                                rows = []
                                for code in merged:
                                    if code.startswith("^") or code == st.session_state.market:
                                        continue
                                    rows.append(
                                        {
                                            "ticker": code,
                                            "sector": sector_lookup.get(code, "Lainnya"),
                                            "roe": None,
                                            "pbv": None,
                                            "cr": None,
                                            "as_of": today,
                                        }
                                    )
                                current_fundamentals = pd.DataFrame(rows)
                            else:
                                existing = set(current_fundamentals["ticker"].astype(str).str.upper())
                                new_rows = []
                                for code in selected:
                                    if code in existing:
                                        continue
                                    new_rows.append(
                                        {
                                            "ticker": code,
                                            "sector": sector_lookup.get(code, "Lainnya"),
                                            "roe": None,
                                            "pbv": None,
                                            "cr": None,
                                            "as_of": today,
                                        }
                                    )
                                if new_rows:
                                    current_fundamentals = pd.concat(
                                        [current_fundamentals, pd.DataFrame(new_rows)],
                                        ignore_index=True,
                                    )
                            if not current_fundamentals.empty:
                                st.session_state.fundamentals = current_fundamentals
                            try:
                                fetch_fundamentals_for(selected)
                            except Exception as exc:
                                st.session_state["fundamental_warnings"] = [f"Fundamental: {exc}"]
                            st.success(f"{len(new_datasets)} instrumen dimuat dari yfinance.")
                            st.rerun()
                    except Exception as exc:
                        st.error(f"Gagal mengambil data: {exc}")
        st.caption("Sumber yfinance memakai harga adjusted. Kode di luar ticker_universe.csv ditolak.")
    elif not st.session_state.assistant_messages:
        st.caption("Contoh: semua saham sawit, seluruh ticker perbankan, semen, atau consumer staples.")
    else:
        st.caption("Belum ada ticker. Coba kata kunci industri lain.")


init_state()

st.title("QuantLab")
st.caption("Analisa return, CAPM & Jensen, dan risiko portofolio dengan benchmark IHSG.")

with st.sidebar:
    st.subheader("Sumber data")
    source = st.radio("Pilih sumber", ["Upload CSV investing.com", "yfinance"], label_visibility="collapsed")
    uploaded = None
    if source == "Upload CSV investing.com":
        uploaded = st.file_uploader(
            "File CSV (boleh lebih dari satu)",
            type=["csv"],
            accept_multiple_files=True,
        )
        st.caption("Setiap file = satu instrumen. Mapping selalu dikonfirmasi.")
    else:
        tickers_text = st.text_input("Kode saham (pisah koma)", value="INDF,LPPF,ANTM")
        benchmark_text = st.text_input("Benchmark", value="^JKSE")
        start_date = st.date_input("Mulai", value=pd.Timestamp("2024-01-01"))
        end_date = st.date_input("Selesai", value=pd.Timestamp.today().normalize())
        st.caption("yfinance memakai harga adjusted (split dan dividen).")
        if st.button("Ambil dari yfinance", width="stretch"):
            tickers = [ticker.strip().upper() for ticker in tickers_text.split(",") if ticker.strip()]
            benchmark = benchmark_text.strip().upper()
            if not tickers:
                st.error("Isi minimal satu kode saham.")
            else:
                with st.spinner("Mengambil harga dan fundamental dari yfinance..."):
                    try:
                        prices = fetch_prices(
                            tickers + [benchmark],
                            start=str(start_date),
                            end=str(end_date),
                        )
                        datasets: dict[str, dict] = {}
                        for code in prices.columns:
                            frame = pd.DataFrame({code: prices[code]}).dropna()
                            if frame.empty:
                                continue
                            datasets[code] = {
                                "frame": frame,
                                "source_period": detect_frequency(frame.index),
                                "mode": "price",
                                "label_change": False,
                                "file": "yfinance",
                            }
                        if len(datasets) < 2:
                            st.error("Data tidak cukup. Cek kode saham dan rentang tanggal.")
                        else:
                            merged = merge_datasets(st.session_state.datasets, datasets)
                            st.session_state.datasets = merged
                            if st.session_state.market not in merged:
                                st.session_state.market = (
                                    benchmark if benchmark in merged else next(iter(merged))
                                )
                            try:
                                fetch_fundamentals_for(tickers)
                            except Exception as exc:
                                st.session_state["fundamental_warnings"] = [f"Fundamental: {exc}"]
                            st.success(f"{len(datasets)} instrumen ditambahkan. Total {len(merged)}.")
                            st.rerun()
                    except Exception as exc:
                        st.error(f"Gagal mengambil data: {exc}")

    if st.session_state.datasets:
        with st.expander("Pengaturan analisa", expanded=True):
            options = list(st.session_state.datasets)
            default_market = st.session_state.market
            if default_market not in options:
                default_market = "IHSG" if "IHSG" in options else options[0]
            market = st.selectbox("Benchmark", options, index=options.index(default_market))
            st.session_state.market = market
            sources = {normalize_period(dataset["source_period"]) for dataset in st.session_state.datasets.values()}
            if len(sources) > 1:
                st.error("Frekuensi sumber berbeda. Samakan dulu: " + ", ".join(sorted(sources)))
                st.stop()
            modes = {dataset["mode"] for dataset in st.session_state.datasets.values()}
            if len(modes) > 1:
                st.error("Sumber return campur: sebagian dari Change %, sebagian dari harga. Samakan pilihan per file.")
                st.stop()
            source_period = sources.pop()
            period_options = allowed_periods(source_period)
            period = st.selectbox(
                "Periode analisa",
                period_options,
                index=len(period_options) - 1,
                format_func=lambda value: PERIOD_LABEL[value],
            )
            if normalize_period(period) != source_period:
                handling = st.radio(
                    "Periode berbeda dari sumber",
                    ["Hitung return dari harga", "Tetap pakai periode sumber"],
                    index=0,
                )
                if handling.startswith("Tetap"):
                    period = source_period
                else:
                    st.caption("Change % tidak bisa di-resample. Return dihitung dari harga.")
            rf_percent = st.number_input("Risk-free tahunan (%)", min_value=0.0, max_value=100.0, value=6.0, step=0.1)
            mode_label = st.radio(
                "Mode Rf",
                ["Corrected (Rf dikonversi)", "Legacy (seperti Excel)"],
                index=0,
            )
            legacy = mode_label.startswith("Legacy")
            locale_label = st.radio("Format angka", ["Indonesia (1.234,56)", "English (1,234.56)"], index=0)
            locale = "id" if locale_label.startswith("Indonesia") else "en"
            decimals = st.slider("Desimal", min_value=1, max_value=4, value=2)
            annualized = st.checkbox("Tampilkan panel annualized", value=False)
            if st.button("Reset data", width="stretch"):
                st.session_state.datasets = {}
                st.session_state.market = None
                st.session_state.upload_signature = None
                st.session_state.pop("remove_datasets", None)
                parse_upload.clear()
                st.rerun()
            if uploaded and st.button("Ubah mapping", width="stretch"):
                st.session_state.upload_signature = None
                st.rerun()
        with st.expander("Detail data"):
            detail_rows = []
            for code, dataset in st.session_state.datasets.items():
                detail_rows.append(
                    {
                        "Kode": code,
                        "Baris": len(dataset["frame"]),
                        "Frekuensi": PERIOD_LABEL[normalize_period(dataset["source_period"])],
                        "Return": "Change %" if dataset["mode"] == "change" else "Harga",
                        "File": dataset["file"],
                    }
                )
            st.dataframe(pd.DataFrame(detail_rows), width="stretch", hide_index=True)
            remove = st.multiselect(
                "Hapus instrumen",
                options=list(st.session_state.datasets),
                key="remove_datasets",
            )
            if remove and st.button("Hapus terpilih", key="remove_button"):
                for code in remove:
                    st.session_state.datasets.pop(code, None)
                remaining = list(st.session_state.datasets)
                st.session_state.market = remaining[0] if remaining else None
                st.session_state.pop("remove_datasets", None)
                st.rerun()
        st.caption("Perhitungan berjalan lokal di mesin ini.")
    else:
        period = "M"
        rf_percent = 6.0
        legacy = False
        locale = "id"
        decimals = 2
        annualized = False

if uploaded:
    signature = tuple(sorted((file.name, file.size) for file in uploaded))
    show_mapping = st.session_state.upload_signature != signature
    parsed_files: dict[str, csv_io.ParsedCsv] = {}
    for file in uploaded:
        try:
            parsed_files[file.name] = parse_upload(file.name, file.getvalue())
        except Exception as exc:
            st.error(f"{file.name}: {exc}")
    if parsed_files and show_mapping:
        st.subheader("Konfirmasi mapping")
        st.caption("Selalu dikonfirmasi. Setiap file menjadi satu instrumen; kode boleh diubah.")
        st.caption("Data lama tetap disimpan; kode yang sama akan diperbarui.")
        st.caption("Harga dari investing.com umumnya tidak adjusted; cek split dan dividen.")
        with st.form("mapping_form"):
            configs: list[dict] = []
            for filename, parsed in parsed_files.items():
                suggested = csv_io.suggest_mapping(parsed)
                columns = list(parsed.frame.columns)
                default_code = dataset_code_from_filename(filename)
                with st.expander(f"{filename} — {len(parsed.frame)} baris", expanded=len(parsed_files) == 1):
                    code = st.text_input("Kode instrumen", value=default_code, key=f"code_{filename}")
                    date_index = columns.index(suggested["date_column"]) if suggested["date_column"] in columns else 0
                    price_index = columns.index(suggested["price_column"]) if suggested["price_column"] in columns else 0
                    date_column = st.selectbox("Kolom tanggal", columns, index=date_index, key=f"date_{filename}")
                    price_column = st.selectbox("Kolom harga", columns, index=price_index, key=f"price_{filename}")
                    change_options = ["—"] + columns
                    if suggested["change_column"] in columns:
                        change_index = change_options.index(suggested["change_column"])
                    else:
                        change_index = 0
                    change_column = st.selectbox(
                        "Kolom Change % (opsional)",
                        change_options,
                        index=change_index,
                        key=f"change_{filename}",
                    )
                    if change_column == "—":
                        change_column = None
                    mode_options = ["Change % (dari file)", "Hitung dari harga"]
                    mode_index = 0 if change_column else 1
                    return_mode = st.radio("Sumber return", mode_options, index=mode_index, key=f"mode_{filename}")
                    label_change = st.checkbox(
                        "Tampilkan return harga sebagai Change %",
                        value=False,
                        key=f"label_{filename}",
                        disabled=return_mode.startswith("Change"),
                    )
                    st.caption(
                        f"Deteksi: delimiter '{parsed.detection.delimiter}', desimal '{parsed.detection.decimal}', "
                        f"tanggal {parsed.detection.date_format or 'manual'}. "
                        f"Frekuensi data: {PERIOD_LABEL.get(detect_frequency(pd.to_datetime(pd.Series(parsed.frame[date_column]), errors='coerce', dayfirst=parsed.detection.decimal == ',').dropna()), 'D')}."
                    )
                    st.dataframe(parsed.frame.head(10), width="stretch", hide_index=True, height=230)
                    configs.append(
                        {
                            "filename": filename,
                            "code": code.strip().upper(),
                            "date_column": date_column,
                            "price_column": price_column,
                            "change_column": change_column,
                            "mode": "change" if return_mode.startswith("Change") else "price",
                            "label_change": label_change,
                        }
                    )
            submitted = st.form_submit_button("Terapkan mapping & hitung", type="primary")
        if submitted:
            codes = [config["code"] for config in configs]
            if any(not code for code in codes):
                st.error("Kode instrumen tidak boleh kosong.")
            elif len(set(codes)) != len(codes):
                st.error("Kode instrumen harus unik.")
            else:
                datasets: dict[str, dict] = {}
                errors: list[str] = []
                for config in configs:
                    parsed = parsed_files[config["filename"]]
                    try:
                        mapping = build_mapping(
                            parsed,
                            config["code"],
                            config["date_column"],
                            config["price_column"],
                            config["change_column"],
                        )
                        frame = csv_io.apply_mapping(parsed, mapping)
                        if len(frame) < 2:
                            raise ValueError("Data valid kurang dari dua baris.")
                        datasets[config["code"]] = {
                            "frame": frame,
                            "source_period": detect_frequency(frame.index),
                            "mode": config["mode"],
                            "label_change": config["label_change"],
                            "file": config["filename"],
                        }
                    except Exception as exc:
                        errors.append(f"{config['filename']}: {exc}")
                if errors:
                    for message in errors:
                        st.error(message)
                else:
                    merged = merge_datasets(st.session_state.datasets, datasets)
                    st.session_state.datasets = merged
                    if st.session_state.market not in merged:
                        st.session_state.market = "IHSG" if "IHSG" in merged else next(iter(merged))
                    st.session_state.upload_signature = signature
                    st.success("Mapping diterapkan. Data lama tetap disimpan.")
                    st.rerun()

if uploaded and st.session_state.datasets and not show_mapping:
    st.caption("Mapping tersimpan. Gunakan tombol Ubah mapping di sidebar bila ingin meninjau ulang.")

datasets = st.session_state.datasets
if not datasets:
    st.info("Mulai dengan mengunggah CSV investing.com di sidebar, atau ambil data lewat yfinance.")
    steps = st.columns(3)
    steps[0].markdown("**1. Muat data**\n\nUnggah CSV investing.com atau tarik harga lewat yfinance.")
    steps[1].markdown("**2. Konfirmasi mapping**\n\nPilih kolom tanggal, harga, dan Change %. Setiap file menjadi satu instrumen.")
    steps[2].markdown("**3. Baca hasil**\n\nPilih benchmark dan periode, lalu sortir grid serta baca panel CAPM dan risiko.")
    st.markdown(
        """
        <div class="ql-note">
        Change % dipakai bila tersedia; bila tidak ada, return dihitung dari harga dan bisa ditampilkan sebagai Change %.
        Harga investing.com umumnya tidak adjusted, sedangkan yfinance memakai harga adjusted.
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.divider()
    render_assistant("empty")
    st.stop()

returns, display_frames, change_labels = compute_returns(datasets, period)
if st.session_state.market not in returns.columns:
    st.error("Benchmark tidak ada di data return.")
    st.stop()

date_min = returns.index.min().date()
date_max = returns.index.max().date()
with st.sidebar:
    date_range = st.date_input(
        "Rentang tanggal",
        value=(date_min, date_max),
        min_value=date_min,
        max_value=date_max,
    )
if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = date_min, date_max
window = returns.loc[pd.Timestamp(start_date) : pd.Timestamp(end_date)]
if len(window) < 2:
    st.warning("Rentang tanggal terlalu pendek. Minimal dua observasi.")
    st.stop()

results = analyze_universe(
    window,
    st.session_state.market,
    rf_annual=rf_percent / 100.0,
    period=period,
    legacy=legacy,
)
if not results:
    st.warning("Tidak ada saham yang bisa dianalisa. Pastikan benchmark berbeda dari saham.")
    st.stop()

best_alpha = max(
    results.items(),
    key=lambda item: item[1].alpha if item[1].alpha is not None else float("-inf"),
)
metric_columns = st.columns(5)
metric_columns[0].metric("Observasi", f"{len(window)}")
metric_columns[1].metric("Periode", PERIOD_LABEL[normalize_period(period)])
metric_columns[2].metric("Benchmark", st.session_state.market)
metric_columns[3].metric("Saham", f"{len(results)}")
alpha_value = best_alpha[1].alpha
alpha_text = "N/A" if alpha_value is None else f"{alpha_value * 100:.2f}%"
metric_columns[4].metric("Alpha terbaik", f"{best_alpha[0]} {alpha_text}")

first_source = datasets[next(iter(datasets))]["source_period"]
chips = [
    f'<span class="ql-badge ql-badge-neutral">{len(datasets)} instrumen</span>',
    f'<span class="ql-badge ql-badge-neutral">Sumber {PERIOD_LABEL[normalize_period(first_source)]}</span>',
    f'<span class="ql-badge ql-badge-neutral">As-of {window.index.max().date()}</span>',
    f'<span class="ql-badge {"ql-badge-warn" if legacy else "ql-badge-ok"}">{"Legacy Excel" if legacy else "Corrected"}</span>',
]
st.markdown(" ".join(chips), unsafe_allow_html=True)
st.caption(source_note(first_source, period, datasets[next(iter(datasets))]["mode"]))
st.divider()

tab_assistant, tab_grid, tab_capm, tab_risk, tab_sector, tab_method = st.tabs(
    ["Asisten AI", "Grid Data", "CAPM & Jensen", "Risiko & Korelasi", "Sektor & Kuadran", "Metodologi"]
)

with tab_assistant:
    render_assistant("analysis")

with tab_grid:
    fields = st.multiselect(
        "Kolom yang ditampilkan",
        options=FIELD_ORDER,
        default=["return"],
        format_func=lambda value: FIELD_LABELS[value],
    )
    st.caption("Klik header kolom untuk sort, pakai menu filter untuk menyaring baris.")
    display, percent_columns, volume_columns = build_display_frame(
        window,
        {code: frame for code, frame in display_frames.items()},
        fields,
        change_labels,
    )
    missing_fields = [field for field in fields if field == "change" and not any(
        f"{code}_change" in display_frames[code].columns for code in display_frames
    )]
    if missing_fields:
        st.info("Kolom Change % tidak tersedia pada data ini. Pilih Return % untuk hasil hitungan harga.")
    if display.empty or len(display.columns) <= 1:
        st.warning("Pilih minimal satu kolom.")
    else:
        render_grid(display, percent_columns, volume_columns, locale, decimals)
        csv_bytes = display.to_csv(index=False).encode("utf-8-sig")
        capm_frame = metrics_table(results, annualized=annualized, locale=locale, decimals=decimals)
        risk_frame = risk_table(results, locale=locale, decimals=decimals)
        corr_frame = correlation_table(window)
        xlsx_bytes = frames_to_excel(
            {
                "Grid": display,
                "CAPM": capm_frame,
                "Risiko": risk_frame,
                "Korelasi": corr_frame,
            },
            {"Grid": percent_columns},
        )
        download_columns = st.columns(2)
        download_columns[0].download_button(
            "Unduh CSV",
            data=csv_bytes,
            file_name="quantlab_grid.csv",
            mime="text/csv",
            width="stretch",
        )
        download_columns[1].download_button(
            "Unduh XLSX",
            data=xlsx_bytes,
            file_name="quantlab.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )

with tab_capm:
    st.subheader("CAPM & Jensen")
    st.dataframe(
        metrics_table(results, annualized=annualized, locale=locale, decimals=decimals),
        width="stretch",
        hide_index=True,
    )
    st.caption(
        "Beta dihitung dari kovariansi return saham dan benchmark. "
        "Alpha positif berarti outperfom relatif terhadap CAPM."
    )
    if legacy:
        st.warning("Mode legacy memakai Rf tahunan langsung pada return periode, seperti Excel. Gunakan corrected untuk keputusan.")
    else:
        st.success("Mode corrected: Rf tahunan dikonversi ke periode analisa.")
    notes = sorted({note for result in results.values() for note in result.notes})
    for note in notes:
        st.caption(note)

with tab_risk:
    st.subheader("Standar Deviasi & Koefisien Variasi")
    st.dataframe(
        risk_table(results, locale=locale, decimals=decimals),
        width="stretch",
        hide_index=True,
    )
    st.caption("CV hanya valid bila rata-rata return positif. Nilai negatif pada mode legacy bukan ukuran efisiensi.")
    st.subheader("Matriks Korelasi")
    corr = correlation_table(window)
    styled = corr.style.map(correlation_style).format("{:.2f}")
    st.dataframe(styled, width="stretch")
    st.caption("Pasangan dengan korelasi rendah (< 0,30) memberi potensi pengurangan risiko portofolio.")

with tab_sector:
    st.subheader("Benchmark Sektor & Kuadran")
    st.caption(
        "Fundamental bisa diisi manual, upload CSV, atau ambil dari yfinance. "
        "Median dihitung dari peer satu sektor, bukan ambang global. "
        "Kuadran menggabungkan kualitas fundamental relatif dengan alpha hasil analisa return."
    )
    fundamental_warnings = st.session_state.pop("fundamental_warnings", None)
    if fundamental_warnings:
        st.warning("Sebagian fundamental tidak terambil: " + "; ".join(fundamental_warnings[:6]))
    sector_map = benchmarks.load_sector_map(SECTOR_MAP_PATH)
    if st.session_state.fundamentals is None:
        initial = None
        if FUNDAMENTALS_PATH.exists():
            try:
                initial = benchmarks.load_fundamentals(FUNDAMENTALS_PATH, roe_percent=True)
            except Exception as exc:
                st.warning(f"File fundamental tersimpan tidak terbaca: {exc}")
        if initial is None or initial.empty:
            initial = benchmarks.template_fundamentals(list(results), sector_map)
        st.session_state.fundamentals = initial
    fundamentals = st.session_state.fundamentals
    template = benchmarks.template_fundamentals(list(results), sector_map)

    input_mode = st.radio(
        "Sumber fundamental",
        ["Editor tabel", "Upload CSV", "yfinance"],
        horizontal=True,
        key="fund_mode",
    )
    if input_mode == "Editor tabel":
        editor_frame = fundamentals.copy()
        for column in ("ticker", "sector", "as_of"):
            if column not in editor_frame.columns:
                editor_frame[column] = ""
        for column in ("roe", "pbv", "cr"):
            if column not in editor_frame.columns:
                editor_frame[column] = None
            editor_frame[column] = pd.to_numeric(editor_frame[column], errors="coerce")
        editor_frame["roe"] = editor_frame["roe"] * 100.0
        edited = st.data_editor(
            editor_frame[["ticker", "sector", "roe", "pbv", "cr", "as_of"]],
            num_rows="dynamic",
            width="stretch",
            hide_index=True,
            column_config={
                "ticker": st.column_config.TextColumn("Ticker", help="Kode saham, mis. INDF"),
                "sector": st.column_config.TextColumn("Sektor", help="Sektor industri yang sama untuk peer"),
                "roe": st.column_config.NumberColumn("ROE %", format="%.2f"),
                "pbv": st.column_config.NumberColumn("PBV", format="%.2f"),
                "cr": st.column_config.NumberColumn("CR", format="%.2f"),
                "as_of": st.column_config.TextColumn("As-of", help="Tanggal data, mis. 2026-09-30"),
            },
            key="fund_editor",
        )
        try:
            st.session_state.fundamentals = benchmarks.load_fundamentals(edited, roe_percent=True)
            fundamentals = st.session_state.fundamentals
        except Exception as exc:
            st.error(f"Editor fundamental belum valid: {exc}")
    elif input_mode == "Upload CSV":
        uploaded_fund = st.file_uploader(
            "CSV fundamental",
            type=["csv"],
            key="fund_upload",
            help="Kolom: ticker, sector, roe, pbv, cr, as_of",
        )
        roe_percent = st.checkbox("ROE dalam persen (15 = 15%)", value=True, key="fund_roe_percent")
        if uploaded_fund is not None:
            signature = (uploaded_fund.name, uploaded_fund.size)
            if st.session_state.get("fund_signature") != signature:
                try:
                    st.session_state.fundamentals = benchmarks.load_fundamentals(
                        uploaded_fund.getvalue(),
                        roe_percent=roe_percent,
                    )
                    st.session_state["fund_signature"] = signature
                    st.session_state.pop("fund_editor", None)
                    fundamentals = st.session_state.fundamentals
                    st.success("Fundamental dari CSV dimuat.")
                except Exception as exc:
                    st.error(f"CSV fundamental gagal dibaca: {exc}")
            else:
                fundamentals = st.session_state.fundamentals
    else:
        st.caption(
            "ROE memakai TTM return on equity, PBV memakai harga terakhir, "
            "CR memakai laporan terakhir. Bank biasanya tidak punya CR. "
            "Nilai yang kosong tidak diisi 0."
        )
        overwrite_fundamentals = st.checkbox(
            "Timpa nilai manual yang sudah ada",
            value=False,
            key="fund_overwrite",
        )
        fetch_tickers = [str(code) for code in results if not str(code).startswith("^")]
        if st.button("Ambil/Refresh fundamental dari yfinance", width="stretch"):
            if not fetch_tickers:
                st.warning("Belum ada saham untuk diambil fundamentalnya.")
            else:
                try:
                    with st.spinner("Mengambil ROE, PBV, dan CR dari yfinance..."):
                        incoming = fetch_fundamentals_for(
                            fetch_tickers,
                            overwrite=overwrite_fundamentals,
                            label="Mengambil fundamental",
                        )
                    if incoming is not None:
                        st.toast(f"Fundamental {len(incoming)} ticker diperbarui.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Gagal mengambil fundamental: {exc}")
        if fundamentals.empty:
            st.info("Belum ada fundamental. Klik tombol di atas untuk mengambil dari yfinance.")
        else:
            preview = fundamentals.copy()
            for column in ("roe", "pbv", "cr"):
                if column not in preview.columns:
                    preview[column] = None
                preview[column] = pd.to_numeric(preview[column], errors="coerce")
            preview["roe"] = preview["roe"] * 100.0
            st.dataframe(
                preview[["ticker", "sector", "roe", "pbv", "cr", "as_of"]],
                width="stretch",
                hide_index=True,
                column_config={
                    "ticker": st.column_config.TextColumn("Ticker"),
                    "sector": st.column_config.TextColumn("Sektor"),
                    "roe": st.column_config.NumberColumn("ROE %", format="%.2f"),
                    "pbv": st.column_config.NumberColumn("PBV", format="%.2f"),
                    "cr": st.column_config.NumberColumn("CR", format="%.2f"),
                    "as_of": st.column_config.TextColumn("As-of"),
                },
            )

    action_columns = st.columns(4)
    if action_columns[0].button("Simpan fundamental", width="stretch"):
        if fundamentals.empty:
            st.warning("Belum ada baris fundamental untuk disimpan.")
        else:
            benchmarks.save_fundamentals(fundamentals, FUNDAMENTALS_PATH, roe_percent=True)
            st.success(f"Tersimpan ke {FUNDAMENTALS_PATH.name}.")
    if action_columns[1].button("Muat file tersimpan", width="stretch"):
        if FUNDAMENTALS_PATH.exists():
            try:
                st.session_state.fundamentals = benchmarks.load_fundamentals(FUNDAMENTALS_PATH, roe_percent=True)
                st.session_state.pop("fund_editor", None)
                st.rerun()
            except Exception as exc:
                st.error(f"Gagal memuat: {exc}")
        else:
            st.info("Belum ada file fundamental tersimpan.")
    if action_columns[2].button("Reset ke template saham", width="stretch"):
        st.session_state.fundamentals = template
        st.session_state.pop("fund_editor", None)
        st.rerun()
    template_csv = template.to_csv(index=False).encode("utf-8-sig")
    action_columns[3].download_button(
        "Unduh template",
        data=template_csv,
        file_name="fundamentals_template.csv",
        mime="text/csv",
        width="stretch",
    )

    as_of_values = [
        str(value)
        for value in fundamentals.get("as_of", pd.Series(dtype=str)).tolist()
        if str(value).strip() and str(value).lower() != "nan"
    ]
    if as_of_values:
        st.caption("As-of data: " + ", ".join(sorted(set(as_of_values))))

    medians = benchmarks.sector_medians(fundamentals)
    quadrants = benchmarks.quadrant_table(fundamentals, medians, results)
    if fundamentals.empty:
        st.info("Isi minimal dua saham satu sektor agar median peer bisa dihitung.")
    else:
        st.markdown("**Median peer per sektor**")
        st.dataframe(
            medians_display(medians, locale=locale, decimals=decimals),
            width="stretch",
            hide_index=True,
        )
        if quadrants.empty:
            st.info("Kuadran belum bisa dihitung.")
        else:
            display_quadrants = quadrant_display(quadrants, locale=locale, decimals=decimals)
            styled_quadrants = display_quadrants.style.map(quadrant_cell_style, subset=["Kuadran"])
            st.dataframe(styled_quadrants, width="stretch", hide_index=True)
            st.caption(
                "Kuadran 1: fundamental di atas median + alpha positif (BUY/CORE). "
                "Kuadran 2: fundamental di atas median + alpha negatif (WATCHLIST). "
                "Kuadran 3: fundamental di bawah median + alpha positif (SPEKULATIF). "
                "Kuadran 4: fundamental di bawah median + alpha negatif (AVOID)."
            )
            if quadrants["Catatan"].astype(str).str.contains("peer", case=False).any():
                st.warning("Ada sektor dengan peer kurang dari dua. Median dan kuadran sektor itu belum sah.")
            quadrant_csv = display_quadrants.to_csv(index=False).encode("utf-8-sig")
            quadrant_xlsx = frames_to_excel(
                {
                    "Kuadran": display_quadrants,
                    "Median": medians_display(medians, locale=locale, decimals=decimals),
                }
            )
            export_columns = st.columns(2)
            export_columns[0].download_button(
                "Unduh kuadran CSV",
                data=quadrant_csv,
                file_name="quantlab_kuadran.csv",
                mime="text/csv",
                width="stretch",
            )
            export_columns[1].download_button(
                "Unduh kuadran XLSX",
                data=quadrant_xlsx,
                file_name="quantlab_kuadran.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
            )

with tab_method:
    st.subheader("Cara hitung")
    st.markdown(
        f"""
        <div class="ql-note">
        <p><strong>Periode.</strong> Data sumber terdeteksi {PERIOD_LABEL[normalize_period(datasets[next(iter(datasets))]['source_period'])]};
        analisa memakai {PERIOD_LABEL[normalize_period(period)]}. Bila berbeda, return dihitung dari harga, bukan menjumlahkan Change %.</p>
        <p><strong>Change %.</strong> Bila kolom Change % tersedia dan periode sama, nilainya dipakai langsung.
        Bila tidak, return dihitung dari harga dan dapat ditampilkan dengan label Change %.</p>
        <p><strong>Rf.</strong> Mode corrected: rf periode = (1 + rf tahunan)^(1/faktor) - 1, dengan faktor 252/52/12.
        Mode legacy meniru Excel: rf tahunan dipakai langsung.</p>
        <p><strong>Beta.</strong> cov(return saham, return benchmark) / var(return benchmark), sampel ddof=1.</p>
        <p><strong>CAPM.</strong> rf + beta x (E(Rm) - rf). Alpha = rata-rata return - CAPM.</p>
        <p><strong>SD & CV.</strong> SD sampel ddof=1; CV = SD / rata-rata, hanya bila rata-rata positif.
        Annualisasi SD memakai akar faktor periode.</p>
        <p><strong>Sektor & kuadran.</strong> Median ROE, PBV, dan CR dihitung dari peer satu sektor yang kamu isi.
        Fundamental dianggap di atas median bila mayoritas metrik lebih baik: ROE lebih tinggi, PBV lebih rendah,
        CR minimal sama dengan median. Kuadran hanya dihitung bila peer minimal dua dan alpha tersedia.</p>
        <p><strong>Sumber harga.</strong> CSV investing.com umumnya tidak adjusted; yfinance memakai harga adjusted.
        Selalu catat tanggal as-of fundamental agar perbandingan sektor bisa diaudit.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
