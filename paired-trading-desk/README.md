# Paired desk

Meja trading paper yang memasangkan lima repositori sesuai pekerjaan yang sudah mereka tulis sendiri. Siklus bawaan berjalan tanpa API key, tanpa RPC, dan tanpa mengirim order sungguhan.

```bash
cd paired-trading-desk
python3 paired-desk demo
python3 paired-desk serve
```

Dashboard ada di `http://127.0.0.1:8765`. Tombol di halaman itu hanya memutar ulang data fixture.

Folder ini bukan bagian dari Checkstyle. Lisensinya MIT, terpisah dari LGPL repositori induk.

## Pasangan

| Repositori | Pekerjaan yang dipertahankan | Di meja ini |
|---|---|---|
| [Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) | Riset, backtest, buku paper | Gerbang pertama. SMA 5/15 harus long, imbal hasil tidak negatif, dan drawdown di bawah batas. Kalau tidak, tidak ada order. |
| [AI Hedge Fund](https://github.com/virattt/ai-hedge-fund) | Komite analis, putuskan di T, isi di T+1, tidak mengirim order live | Empat suara sistematis (tren, momentum, regangan, drawdown) untuk saham. Fill ekuitas dicap `ai_hedge_fund`. |
| [Hummingbot](https://github.com/hummingbot/hummingbot) | Eksekusi CEX dan paper trade | BTC-USDT. Fill dicap `hummingbot`. Perintah `hbot` memakai `binance_paper_trade`. |
| [pumpfun-bonkfun-bot](https://github.com/chainstacklabs/pumpfun-bonkfun-bot) | Launchpad Solana: pump.fun, letsbonk, LaunchLab | Jalur terpisah. Hanya jalan bila skor BTC risk-on, umur token lolos, dan platform ada di daftar. TP/SL dihitung di buku SOL paper. |
| [Grok Build](https://github.com/xai-org/grok-build) | Agen operator | Skill di `.grok/skills/paired-desk`. `paired-desk operator` merangkum laporan. Grok hanya dipanggil bila `engines.grok` diubah ke `delegate` dan Anda memberi `--ask`. |

`CHOP` ada di fixture untuk memperlihatkan gerbang: harga jatuh, riset menolak, komite tidak membelinya.

## Perintah

```bash
python3 paired-desk demo          # putar ulang fixture, tulis var/demo/
python3 paired-desk run           # sama, tulis var/paper/
python3 paired-desk run --fetch   # ganti BTC-USDT dengan kline harian publik Binance
python3 paired-desk status
python3 paired-desk doctor
python3 paired-desk halt --reason "cek dulu"
python3 paired-desk resume
python3 paired-desk handoff       # yaml/perintah untuk aihf, hbot, pump_bot
python3 paired-desk operator
python3 paired-desk serve --port 8765
```

Setiap `demo` dan `run` memutar data dari awal. Bukan tick yang menyambung sesi kemarin. Kill switch di folder state yang sama membatalkan fill pada putaran berikutnya.

Uji:

```bash
python3 -m unittest discover -s tests -v
```

## Menghubungkan alat aslinya

`doctor` melaporkan binary yang ada di PATH: `vibe-trading`, `aihf`, `hbot`, `pump_bot`, `grok`. Tanpa binary itu, meja tetap memakai mesin paper bawaan.

`handoff` menulis tiga file di `var/handoff/`:

- `aihf-mandate.yaml` — mandat schema 2 untuk `aihf paper create` lalu `aihf paper tick`. Mandat ini tidak berisi ticker; universe ekuitas ada di perintahnya.
- `commands.txt` — `hbot deploy simple_pmm` dengan `exchange=binance_paper_trade`.
- `pump.yaml` — config pumpfun-bonkfun-bot, `enabled: false`, `extreme_fast_mode: false`, kunci hanya sebagai `${SOLANA_PRIVATE_KEY}`.

Untuk menyerahkan satu jalur ke alat aslinya, ubah `engines` di `desk.json` dari `builtin` ke `delegate`, pasang CLI-nya, lalu panggil perintah di `commands.txt`. Eksekusi live tidak menyala karena penggantian itu.

## Live

Live dimatikan dua kali. `desk.json` harus `"mode": "live"`, dan environment harus berisi `PAIRED_DESK_LIVE=I_UNDERSTAND`. `live.exchange` wajib diisi sendiri; meja tidak memilih bursa sungguhan untuk Anda. `live.pump_buy_amount_sol` ditolak kalau lebih dari 0.05 SOL.

```bash
python3 paired-desk live-plan      # menulis file, tidak mengirim order
python3 paired-desk live-execute   # memanggil hbot dan pump_bot bila keduanya terpasang
```

Jangan menaruh private key di `desk.json`, di argv, atau di git. Salin `.env.example` ke `.env` dan biarkan proses upstream yang membacanya.

Ini bukan nasihat investasi. Vibe-Trading, AI Hedge Fund, dan pumpfun-bonkfun-bot ditulis sebagai perangkat belajar. Hummingbot bisa mengirim order sungguhan hanya setelah Anda melewati kedua gerbang di atas.
