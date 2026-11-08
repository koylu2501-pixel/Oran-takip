# Oran takip (mini test)

Her 30 dakikada bir:
- iddaa bülteninden 9 ligin MS 1-0-2 oranlarını kaydeder (`data/iddaa.csv`).
- Premier Lig ve Süper Lig maçları için Pinnacle ve Bet365 MS oranlarını maç başına 2 kez okur: maçtan 30–6 saat önce ve 2 saat–30 dakika önce (`data/pinnacle.csv`). OddsPapi'nin ücretsiz paketi ayda 250 sorgu verir; program 230'da durur.
- Pinnacle bir seçenekte en az %5 düşmüşse ve iddaa hâlâ Pinnacle'ın adil oranından yüksekse Telegram'a sinyal yollar (`data/sinyaller.csv`).
- Her gün 10:00'dan sonra, oynanmış sinyallerde iddaa'nın sonradan düşüp düşmediğini ve kaç dakika gecikmeyle düştüğünü rapor eder.

## Kurulum
Depo ayarlarında: **Settings → Secrets and variables → Actions → New repository secret**
- `TELEGRAM_TOKEN`: BotFather'ın verdiği anahtar
- `ODDSPAPI_KEY`: OddsPapi anahtarı
- `TELEGRAM_CHAT_ID`: isteğe bağlı. Boş bırakırsan bota bir kez `/start` yazman yeterli; program sohbeti kendisi bulur.

İlk çalıştırma: **Actions → oran-takip → Run workflow**.
