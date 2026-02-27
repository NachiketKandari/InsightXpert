# Top 10 Must-Have Analyses for the InsightXpert Leadership Analytics Dashboard

## Dataset Overview

This dashboard is built on 250,000 synthetic Indian UPI transactions spanning January 1 to December 30, 2024. The dataset covers four transaction types (P2P, P2M, Bill Payment, Recharge), ten merchant categories, eight sender and receiver banks, ten Indian states, and includes device, network, temporal, and risk metadata. The average transaction value is ₹1,312, ranging from ₹10 to ₹42,099.

The analyses below are ranked by their combination of business impact, statistical robustness, and actionability for a leadership audience. Each analysis has been validated against actual query results from the dataset.

---

## Analysis 1: Failure Rate by Sender Bank × Receiver Bank Pair

**Priority: Tier 1 — Build First**

### Why It Matters

Payment failure is the single most actionable risk metric in this dataset: 12,376 failed transactions (4.95%) provide a statistically robust signal across virtually every sub-segment. For leadership, failure rates by bank pair directly identify which bank-to-bank corridors are degrading user experience and creating churn risk. This is an operational SLA metric that both the product team and bank partners can act on immediately.

### What to Measure

- Primary metric: `COUNT(*) FILTER (WHERE transaction_status = 'FAILED') / COUNT(*)` as `failure_rate`
- Dimensions: `sender_bank`, `receiver_bank`
- Secondary: absolute failure count per pair to distinguish high-rate/low-volume from high-rate/high-volume corridors
- Columns used: `transaction_status`, `sender_bank`, `receiver_bank`

### Key Finding

Overall failure rate is 4.95%. HDFC has the lowest failure rate among sender banks (4.82%) while Yes Bank has the highest (5.10%). The bank-to-bank pair matrix reveals which specific corridors are outliers — e.g., a high-failure-rate corridor between two mid-tier banks signals an interbank settlement or API reliability issue invisible in aggregate numbers.

### Suggested Visualization

Heatmap with sender banks on the X-axis and receiver banks on the Y-axis. Cell color encodes failure rate (white-to-red scale). Overlay cell text with absolute failure count for context. A separate bar chart ranks individual banks by their outbound (sender) and inbound (receiver) failure rates.

---

## Analysis 2: Transaction Volume and Value by Merchant Category

**Priority: Tier 1 — Build First**

### Why It Matters

Merchant category breakdown reveals where the platform is winning and where the largest growth opportunities lie. Leadership needs to understand both volume share and average ticket size to prioritize category expansion, merchant acquisition, and promotional spend. A category with a high ticket size but low volume is a whitespace opportunity; a high-volume category with low ticket size signals a saturated but engagement-rich segment.

### What to Measure

- `COUNT(*)` as transaction volume per category
- `AVG(amount_inr)` as average ticket size per category
- `SUM(amount_inr)` as total GMV per category
- GMV share (%) across categories
- Columns used: `merchant_category`, `amount_inr`, `transaction_type`

### Key Finding

Education has the highest average ticket at ₹5,097 but only 7,598 transactions — the lowest volume of any category. This gap (high value, low penetration) is the clearest single expansion opportunity in the dataset. Shopping follows at ₹2,584 per transaction. At the other end, Transport (₹307) and Food (₹533) are high-frequency, low-value categories that drive engagement but modest GMV. Grocery (₹1,175) sits in the middle — high volume, moderate ticket — making it the workhorse of everyday UPI usage.

### Suggested Visualization

Bubble chart: X-axis = transaction volume, Y-axis = average ticket size, bubble size = total GMV. Each bubble is a merchant category. This immediately surfaces the Education outlier (small bubble, high on Y-axis) and the Food/Transport cluster (large bubbles, low on Y-axis). Supplement with a stacked bar showing GMV share by category.

---

## Analysis 3: Failure Rate by Device Type × Network Type

**Priority: Tier 1 — Build First**

### Why It Matters

Operational reliability varies significantly by the technology stack the user is on. Leadership and engineering teams need to know whether failures are systemic (affecting all devices/networks) or concentrated in specific combinations that can be targeted with UX fixes, retry logic improvements, or network-specific timeout tuning. This is a direct input to product roadmap prioritization.

### What to Measure

- Failure rate: `FAILED / total` per `device_type` × `network_type` combination
- Volume per combination (to distinguish signal from noise)
- Columns used: `transaction_status`, `device_type`, `network_type`

### Key Finding

The Web + 3G combination is the worst-performing segment with a 6.6% failure rate — substantially above the 4.95% average. Android accounts for 75% of volume (187,777 transactions) and iOS 20% (49,613), making Android reliability the platform's primary concern by volume. Web on any network shows elevated failure rates relative to native apps. 5G transactions (25% of volume) represent the improving baseline, while 3G (5% of volume) is the tail-end degraded experience.

### Suggested Visualization

Grouped bar chart with device type on the X-axis, bars grouped by network type, bar height encoding failure rate. Annotate each bar with transaction volume. An alternative is a 3×4 heatmap (device × network) with failure rate as color intensity.

---

## Analysis 4: Transaction Type Mix — Volume, Value, and Failure by Type

**Priority: Tier 1 — Build First**

### Why It Matters

The P2P/P2M/Bill Payment/Recharge split is the foundational segmentation of any UPI platform. Each type has a different revenue model, failure tolerance, and user expectation. Leadership needs this as a baseline view to contextualize every other metric — failure rates, fraud flags, and ticket sizes all look different within each type, and strategic decisions about merchant partnerships, bill aggregator integrations, or P2P growth campaigns are type-specific.

### What to Measure

- Volume share: `COUNT(*) per transaction_type / total`
- Average ticket size: `AVG(amount_inr)` per type
- Total GMV: `SUM(amount_inr)` per type
- Failure rate per type
- Columns used: `transaction_type`, `amount_inr`, `transaction_status`

### Key Finding

P2P dominates at 45% of volume (112,445 transactions), followed by P2M at 35% (87,660), Bill Payment at 15% (37,368), and Recharge at 5% (12,527). Despite lower volume, P2M and Bill Payment tend toward higher ticket sizes, making them disproportionate contributors to GMV. The 36–45 age group shows the highest average ticket across all transaction types (₹1,415–₹1,436), suggesting that middle-aged users are the high-value P2M and Bill Payment cohort.

### Suggested Visualization

Donut chart for volume share (quick executive view), paired with a horizontal bar chart ranking types by total GMV. A small table below shows failure rate per type. This three-panel layout gives leadership a complete per-type picture in a single glance.

---

## Analysis 5: User Demographic Segmentation — Age Group by Volume, Ticket Size, and Value

**Priority: Tier 1 — Build First**

### Why It Matters

Age-group segmentation directly informs product, marketing, and growth strategy. Knowing which demographic drives volume versus which drives value separates acquisition targets from monetization targets. For leadership, this is the "who is our user" slide — it anchors all subsequent discussions about UX investment, financial product cross-sell, and geographic expansion priorities.

### What to Measure

- `COUNT(*)` per `sender_age_group`
- `AVG(amount_inr)` per age group
- `SUM(amount_inr)` GMV contribution per age group
- Failure rate per age group
- Columns used: `sender_age_group`, `amount_inr`, `transaction_status`

### Key Finding

The 26–35 age group is the dominant cohort by volume (87,432 transactions, 35% of total). The 36–45 group has the highest average ticket size (₹1,415–₹1,436 depending on transaction type). The 56+ segment is the smallest (12,509 transactions) but failure rates in older age groups deserve monitoring — a higher failure rate for 56+ users may indicate UX accessibility friction. The 18–25 cohort (62,345 transactions) represents future platform growth and is nearly equal in volume to the 36–45 group.

### Suggested Visualization

Stacked bar chart: age groups on X-axis, stacked bars showing volume split by transaction type. Overlay a line chart (secondary Y-axis) for average ticket size per age group. This dual-axis view surfaces the 36–45 premium without burying the 26–35 volume story.

---

## Analysis 6: Geographic Performance — State-Level Volume, Value, and Failure Rate

**Priority: Tier 2 — Strong Supporting**

### Why It Matters

State-level performance is essential for any leadership team making decisions about geographic expansion, regional partnerships, or regulatory engagement. Understanding where the platform is strong (Maharashtra), where quality is lagging (failure rate hot spots), and where high-value behavior is concentrated (Rajasthan's higher average ticket) allows resource allocation to be evidence-driven rather than assumption-driven.

### What to Measure

- `COUNT(*)` transaction volume per `sender_state`
- `AVG(amount_inr)` per state
- Failure rate per state
- GMV per state
- Columns used: `sender_state`, `amount_inr`, `transaction_status`

### Key Finding

Maharashtra leads in volume with 37,427 transactions. Rajasthan has the highest average transaction amount at ₹1,338. Failure rates vary modestly across states — no state shows a dramatically outlier failure rate, but combining failure rate with volume identifies states where the absolute count of failed transactions is creating the most user dissatisfaction. Karnataka's elevated fraud flag rate (0.232%, discussed in Analysis 8) is a secondary flag to monitor.

### Suggested Visualization

Choropleth map of India with states colored by transaction volume (primary view) and a toggle to switch the color encoding to failure rate or average ticket size. Supplement with a ranked bar chart for the top 10 states by GMV, since the choropleth alone can obscure small-area high-value states.

---

## Analysis 7: Bank-Level Market Share and Reliability Scorecard

**Priority: Tier 2 — Strong Supporting**

### Why It Matters

Banks are key infrastructure partners in UPI, and their performance directly affects platform reliability. A bank scorecard gives leadership a structured way to have data-backed conversations with banking partners about SLA improvements, escalation paths for high-failure corridors, and strategic decisions about which banks to promote as default payment options in the app UI.

### What to Measure

- Volume share: `COUNT(*)` per `sender_bank`
- Failure rate as sender: `FAILED / total` per `sender_bank`
- Failure rate as receiver: `FAILED / total` per `receiver_bank`
- Average ticket size per bank (as sender)
- Columns used: `sender_bank`, `receiver_bank`, `transaction_status`, `amount_inr`

### Key Finding

SBI is the largest bank by volume with 62,693 transactions. Kotak is the smallest with 20,032. HDFC has the best reliability as a sender bank (4.82% failure rate) while Yes Bank has the highest (5.10%). The 0.28 percentage point spread between best and worst sender banks is modest in percentage terms but translates to hundreds of additional failed transactions at scale. Kotak's slightly elevated fraud flag rate (approximately 0.25%) is worth monitoring but does not yet reach statistical significance.

### Suggested Visualization

Table-based scorecard with one row per bank. Columns: volume, volume share (%), avg ticket, sender failure rate, receiver failure rate, fraud flag rate. Color-code each metric cell using a green-yellow-red gradient. This format is familiar to leadership and allows direct bank-to-bank comparison.

---

## Analysis 8: Fraud Flag Distribution and Concentration Analysis

**Priority: Tier 2 — Strong Supporting (with statistical caveats)**

### Why It Matters

Fraud flag rate is a board-level risk metric for any payments platform, even when absolute counts are low. Leadership needs visibility into which segments show elevated fraud concentration to guide compliance investments, model improvement priorities, and regulatory reporting. However, this analysis must be presented with appropriate confidence intervals to avoid overreacting to noise.

### What to Measure

- Overall fraud flag rate: `SUM(fraud_flag) / COUNT(*)`
- Fraud flag rate by: `merchant_category`, `sender_state`, `sender_bank`, `device_type`
- Absolute fraud flag count per segment (critical context)
- Columns used: `fraud_flag`, `merchant_category`, `sender_state`, `sender_bank`, `device_type`

### Key Finding

The overall fraud flag rate is 0.19% (480 events across 250,000 transactions). Shopping has the highest merchant category fraud rate at approximately 0.260%, which is the strongest fraud signal in the dataset given Shopping's transaction denominator of roughly 14,976 transactions. Karnataka is the only state approaching geographic significance at 0.232%. These findings should be presented alongside confidence intervals — most sub-segment differences are not statistically significant at N=480 total fraud events. The analysis is most useful as a monitoring baseline to track whether rates change over time rather than as a current anomaly detector.

### Suggested Visualization

Bar chart of fraud flag rate by merchant category and by state, with error bars showing 95% confidence intervals. The error bars are essential — they visually communicate to leadership which differences are signal versus noise. Annotate bars with absolute fraud count. A call-out box should note that the 0.19% base rate requires continued monitoring as transaction volume grows for the signal to strengthen.

---

## Analysis 9: Monthly Transaction Trend — Volume, GMV, and Failure Rate Over Time

**Priority: Tier 2 — Strong Supporting**

### Why It Matters

Time-series trend analysis is the foundational "health of the business" view for any executive dashboard. Even in a dataset with near-flat seasonality, month-over-month consistency is itself a business insight: it tells leadership that the platform has no seasonal tailwinds or risks, that growth will be driven by product and marketing rather than calendar effects, and that the platform's reliability is consistent across the year.

### What to Measure

- `COUNT(*)` transactions per month
- `SUM(amount_inr)` GMV per month
- Failure rate per month: `FAILED / total`
- Columns used: any date-derivable column (inferred from `hour_of_day`, `day_of_week`, `is_weekend` — or transaction date if available)

### Key Finding

Monthly volume is remarkably stable at 19,000–21,000 transactions per month. January is the peak at 21,221 transactions and February is the lowest at 19,759. The month-to-month variation is under 7%, indicating near-zero seasonality. This means any future deviation from the 19k–21k band would be a meaningful signal requiring investigation. Monthly failure rate trends should be overlaid to detect whether any reliability degradation is emerging.

### Suggested Visualization

Dual-axis line chart: left Y-axis for transaction volume (line + shaded area), right Y-axis for failure rate (line). X-axis is month. Add a reference band showing ±1 standard deviation from the mean volume to make the "unusually high or low" threshold explicit. A secondary panel can show GMV trend on the same time axis.

---

## Analysis 10: Peak Hour and Day-of-Week Usage Patterns

**Priority: Tier 3 — Include with Caveats**

### Why It Matters

Usage timing patterns inform infrastructure capacity planning and the scheduling of maintenance windows, promotional campaigns, and customer support staffing. An evening peak, for example, tells engineering when to avoid deployments and tells marketing when push notifications will get the highest engagement. This is primarily an operational input rather than a strategic one.

### What to Measure

- `COUNT(*)` per `hour_of_day`
- `COUNT(*)` per `day_of_week`
- Failure rate per `hour_of_day` (volume-adjusted, not raw count)
- `is_weekend` volume split
- Columns used: `hour_of_day`, `day_of_week`, `is_weekend`, `transaction_status`

### Key Finding

Transaction volume peaks at 19:00 (7 PM) with 21,232 transactions — consistent with evening post-work usage behavior. Weekend vs. weekday volumes are nearly identical at approximately 35,000 transactions per day each, indicating that UPI has become a daily habit independent of work schedules. Late-night hours (1–3 AM) show slightly elevated fraud flag rates, but the absolute event counts are 3–8 fraud flags per hour — far too small for statistical inference. Day-of-week fraud patterns (Sunday 0.208% vs. Tuesday 0.163%) are not statistically significant and should not drive operational decisions.

### Suggested Visualization

Heat map with hour of day (0–23) on X-axis and day of week on Y-axis, cell color encoding transaction volume. This is the standard "activity calendar" view familiar to operations teams. Failure rate can be shown in a companion heat map with the same axes. Do not use the same visualization for fraud flag rate — the cell-level event counts are too small to be meaningful.

---

## What Was Intentionally Excluded

### Day-of-Week Fraud Sub-Patterns

Sunday has a 0.208% fraud flag rate and Tuesday has 0.163%. This was excluded from the main analyses because with only 480 total fraud events, splitting further by 7 days of the week yields roughly 50–80 events per day — well below the threshold for statistical confidence. The observed variation is almost certainly sampling noise. Including this as a dashboard widget risks driving operational decisions based on artifacts.

### Hour-of-Day Fraud Rate Analysis

Late-night hours (1–3 AM) appear to have elevated fraud rates when expressed as a percentage, but the absolute numerators are 3–8 fraud flag events per hour. A single misclassified transaction changes the rate by more than 10 percentage points. This analysis should not appear on a leadership dashboard until the dataset grows by an order of magnitude or the fraud flag definition is tightened.

### Network Type as a Standalone Dimension

Network type (4G/5G/WiFi/3G) is valuable in combination with device type (Analysis 3) but weak as a standalone view. The 3G cohort is 5% of volume, and its elevated failure rate is already captured in the device × network combination. A standalone network breakdown adds little incremental insight for leadership.

### Bank-to-Bank Fraud Rate Matrix

The bank × bank fraud flag matrix (8 × 8 = 64 cells) would yield an average of 7.5 fraud events per cell. At that count, confidence intervals span the entire 0%–1% range, making every cell reading meaningless. This is excluded in favor of the bank reliability scorecard (Analysis 7), which uses failure rate — a signal with 12,376 events — for the bank-level risk view.

### P2P vs. P2M Fraud Comparison

While segmenting fraud by transaction type is conceptually appealing, the denominator problem is severe: 112,445 P2P transactions with roughly 213 fraud flags gives a rate of ~0.19%, and similar math applies to other types. The confidence intervals overlap completely. This comparison should be revisited when the fraud event count exceeds 5,000.
