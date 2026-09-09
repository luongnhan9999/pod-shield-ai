# PodShield AI (Autonomous AI Podcast & Media Sponsorship Ad-Placement Escrow)

PodShield AI is a standalone GenLayer Intelligent Contract primitive that solves the trust and verification problem in podcast, video, and media sponsorships. 

Brands lock their sponsorship budgets in escrow, and creators stake a commitment bond to accept deals. Once the creator publishes the episode, the contract automatically fetches the episode content, triggers GenLayer's AI consensus to audit the transcript, and disburses the escrow budget based on a semantic verification of the ad-read.

---

## 🚀 Deployment Info

*   **Network**: `studionet` (GenLayer Studio Network)
*   **Contract Address**: `0x671C65Ae5283C3200F1Ba57323ed7f0fad1bE55a`

---

## 💡 How the AI Consensus & Custom Validator Works

Rather than relying on brittle keyword matching or exact string checks (which fail due to ad-libbing, pronunciation, transcription noise, or phrasing variations), PodShield AI leverages GenLayer's non-deterministic AI consensus to audit the ad-read.

1.  **Semantic Evaluation**: Multiple independent validator nodes render the episode page, fetch the transcript, and prompt an LLM to evaluate if the creator met the talking points, read the sponsor script correctly, and mentioned the exact promo code/link.
2.  **Validator Agreement on MEANING**: The custom validator function (`validator_fn`) enforces consensus by requiring the nodes to agree on the semantic outcome (**Verdict** and **Payout Percentage**), rather than just checking that the output conforms to a JSON format.
3.  **Divergence Resolution**: If two validator nodes produce different verdicts (e.g. one votes `APPROVED` and another votes `REJECTED`), consensus fails, and the deal is escalated (`ESCALATED`) to prevent automatic payout of disputed deals, allowing the platform arbiter to resolve it.

---

## 🛠️ Public API

### Write Methods

*   **`create_deal(creator_addr: str, creator_channel_base: str, sponsor_script: str, required_promo_code: str) -> str`** *(Payable)*
    Allows a brand to create a deal by specifying the creator's address, the official channel base URL prefix (e.g., `https://my-podcast-host.com/`), the required sponsor talking points/script, and the mandatory promo code/link. The brand sends the sponsorship budget as the transaction value. Returns a unique `deal_id`.
*   **`accept_and_stake(deal_id: str)`** *(Payable)*
    Allows the designated creator to accept the deal by staking a commitment bond (sent as transaction value). Status transitions to `STAKED`.
*   **`cancel_deal(deal_id: str)`**
    Allows the brand to cancel the deal and receive a 100% refund of their budget, but only *before* the creator accepts and stakes.
*   **`commit_episode(deal_id: str, episode_url: str)`**
    **Exclusively called by the designated creator**. Commits the exact public episode URL delivery evidence. The contract validates that `episode_url` starts with `creator_channel_base`. Status transitions to `COMMITTED`. Does not move funds.
*   **`approve_delivery(deal_id: str)`**
    **Called by the brand**. Directly reviews and approves the creator's committed episode, immediately disbursing payout and refunding the creator's bond without requiring AI consensus fees.
*   **`challenge_delivery(deal_id: str)`**
    **Called by the brand**. Challenges the committed episode delivery, triggering GenLayer's autonomous AI consensus on the pre-committed URL.
*   **`adjudicate_deal(deal_id: str)`**
    Called by either creator or brand. Triggers autonomous AI consensus to audit the pre-committed episode evidence (`deal.episode_url`), enforcing consensus on the semantic verdict, payout percentage, and confidence threshold (`>= 65%`).
*   **`resolve_escalated_deal(deal_id: str, creator_percentage: int)`**
    Allows the platform arbiter to manually resolve a deal that has been escalated (`ESCALATED`) due to low LLM confidence or validator divergence.

### View Methods

*   **`get_deal(deal_id: str) -> str`**
    Returns a JSON string containing the detailed state of a deal, including `creator_channel_base`, `episode_url`, `status`, `verdict`, and `confidence`.
*   **`get_deal_counter() -> int`**
    Returns the total number of deals created.
*   **`get_treasury() -> str`**
    Returns the current treasury fee address.

---

## 📝 Worked Example Workflow

Here is a step-by-step example of how a sponsorship deal is executed and settled on-chain:

### 1. Deal Creation (Brand)
*   **Action**: Brand invokes `create_deal` with `1 GEN` budget.
*   **Inputs**:
    *   `creator_addr`: `"0x2bd806c97F0e00aF1a1fC3328fA763a9269723C8"`
    *   `creator_channel_base`: `"https://my-podcast-host.com/"`
    *   `sponsor_script`: `"Support for this podcast comes from PodShield. Get 20% off your first subscription using code POD20 today."`
    *   `required_promo_code`: `"POD20"`
*   **Output**: `deal_id = "1"` (Status: `OPEN`)

### 2. Deal Acceptance (Creator)
*   **Action**: Creator invokes `accept_and_stake("1")` and stakes `0.5 GEN` as a commitment bond.
*   **State transition**: Deal status changes from `OPEN` to `STAKED`.

### 3. Exact Episode Commitment (Creator Only)
*   **Action**: Creator publishes the episode and invokes `commit_episode("1", "https://my-podcast-host.com/episodes/42")`.
*   **Validation**: The contract confirms `episode_url` begins with `https://my-podcast-host.com/` and caller is the creator.
*   **State transition**: Deal status changes to `COMMITTED`. The URL is permanently bound to the deal.

### 4. Review & Adjudication / Challenge
*   **Direct Path**: Brand can review and call `approve_delivery("1")` for immediate settlement.
*   **Autonomous AI Audit Path**: Brand challenges or Creator triggers `adjudicate_deal("1")`.
    *   **Content-Hash Grounding**: Leader fetches the committed episode page and calculates a deterministic SHA-256 fingerprint of the normalized content.
    *   **Consensus Binding**: Validator independently fetches the page and validates that its own content fingerprint exactly matches the leader's. If the page content differs or was modified, consensus fails immediately.
    *   **Fail-Closed Architecture**: If content is too short (< 200 chars), blocked by captcha/404/rate-limit, or if LLM produces malformed output, the contract safely escalates to `ESCALATED` status without moving any escrow funds.
    *   GenLayer AI consensus audits the ad-read. Independent validator nodes agree on the verdict, payout percentage, confidence threshold (`>= 65%`), and content hash.
*   **Consensus Verdict**:
    ```json
    {
      "verdict": "APPROVED",
      "payout_pct": 100,
      "confidence": 95,
      "reason": "The creator successfully read the full script and included the required promo code POD20.",
      "content_hash": "a1b2c3...64-char SHA256"
    }
    ```
*   **Escrow Settlement (Deterministic)**:
    *   Creator Net Payout: `0.98 GEN` (100% budget minus 2% protocol fee).
    *   Treasury Fee: `0.02 GEN` (2% protocol fee).
    *   Bond Returned: `0.5 GEN` returned in full to creator.
    *   **Total Creator Received**: `1.48 GEN`
    *   **Total Treasury Received**: `0.02 GEN`
    *   **Deal Status**: `SETTLED`

---

## 🧪 Testing

The contract is validated with in-memory direct mode tests. To run the tests:

1. Install dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```
2. Run the test suite:
   ```bash
   gltest tests/
   ```
