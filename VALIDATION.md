# Validation — 2.0.0

Base: `laith-rox/laith-bot` commit `d1c945b2daad0bf31b2d3bc9e22b2d8f972d0ea6`.
Date: 2026-09-10.

`python -m unittest -q test_bot`: **43 tests passed** locally. All market data and HTTP transports in this suite are synthetic or mocked. No real Telegram messages or broker orders are emitted by tests.

Verified cases:

- Clock-aligned, complete higher-timeframe candles; current/future/stale candles and invalid OHLC rejected.
- Known EMA and Wilder RSI values; flat RSI handled and extreme RSI cannot be outvoted by scoring.
- Long and short stop/target observation, worse gap-open stops, ambiguous intrabar ordering excluded, next-bar protection, no reuse of pre-announcement extremes or replayed events.
- Persistent restart recovery; one outstanding signal; definite send rejection retried without starting cooldown, acknowledged delivery starts cooldown; expired entries released.
- Telegram rate-limit delay respected; wrong-recipient acknowledgements rejected; read timeout and crash during POST not blindly retried.
- Daily 3R model brake, private-owner command authorization, manual pause and news protection preserve existing-signal monitoring.
- Current-week news calendar, blackout boundaries and unavailable-calendar blocking; secret and traceback suppression.
- End-to-end preparation, delivery acknowledgement, repeated analysis, and existing-signal closure during entry blackout.
- Historical cost monotonicity, explicit missing news coverage, holdout boundary, invalid cost rejection, and historical fills strictly after decision time.

Historical evaluation tooling is included, but this release has **no measured live profitability claim or independently validated historical return**. Production deployment must separately confirm the persistent volume, bot identity, provider data and Telegram acknowledgement from runtime logs. Local tests do not prove those external services are available.

Observational limits and assumptions are documented in README.md. The original `xau-signal-bot` repository and service are outside this change.


## v2.1.0 — 2026-09-10

54 اختبارات آلية ناجحة، منها 11 جديدة: مستويات الاتجاهين، تأكيد الشمعتين ومنع احتساب المكررة أو الفجوة، الاتجاه المعاكس الكامل، عزل الإحصاءات، تأكيد الإرسال، حفظ المتابعة بعد إعادة التشغيل، بوابات الأخبار والإيقاف، استمرار الطوارئ أثناء pause/news، أولوية الإنذار وتصعيده ومنع تكراره، انتهاء المتابعة المبكّرة واستبدالها بإشارة مكتملة.

الأوامر: `python -m unittest -q test_bot`. البيانات صناعية والإرسال محاكًى؛ لا تدل النتائج على دقة مالية أو ربحية. لا اختبارات أداء سوقية جديدة، ولا تغيير لنموذج احتساب نتائج الإشارات المكتملة.


## v2.2.0 — 2026-09-10

62 اختبارًا ناجحًا. أضيفت 8 حالات للمواعيد +0/+5/+10/+15، الاستعادة ومنع التكرار، فشل/انتهاء إرسال التقرير ومنع المتابعة اليتيمة، انقطاع البيانات، التعادل والتفوق الضعيف، تصنيف الشروط المكتملة وحجب المستويات، ضعف/انعكاس الاتجاه، pause مع استمرار متابعة المرسل، طوارئ السيناريو الدوري وعزل إحصاءاته. حُدّث اختبار بوابة الأخبار ليطابق استمرار التقرير المعلوماتي وحجب مستويات الدخول.

بيانات صناعية وإرسال محاكًى، وليست نتائج تداول تاريخية أو حية. أوامر الاختبار كما سبق: `python -m unittest -q test_bot`.
