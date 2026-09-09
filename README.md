# PodShield AI (Autonomous AI Podcast & Media Sponsorship Ad-Placement Escrow)

PodShield AI is a standalone GenLayer Intelligent Contract primitive that solves the trust and verification problem in podcast, video, and media sponsorships. 

Brands lock their sponsorship budgets in escrow, and creators stake a commitment bond to accept deals. Once the creator publishes the episode, the contract automatically fetches the episode content, triggers GenLayer's AI consensus to audit the transcript, and disburses the escrow budget based on a semantic verification of the ad-read.

---

## 🚀 Deployment Info

*   **Network**: `studionet` (GenLayer Studio Network)
*   **Contract Address**: `0x1E1A44D8d11E1813682AdeAF87863A11917628fc`

---

## 💡 How the AI Consensus & Custom Validator Works

Rather than relying on brittle keyword matching or exact string checks (which fail due to ad-libbing, pronunciation, transcription noise, or phrasing variations), PodShield AI leverages GenLayer's non-deterministic AI consensus to audit the ad-read.

1.  **Exact Episode Commitment (No Unrelated URLs)**: To prevent either party from submitting unrelated pages to trigger false payouts or bond slashing, the contract binds evidence strictly to the registered channel base (`creator_channel_base`). Furthermore, **only the creator** can commit the published episode URL (`commit_episode`), or the brand can lock an expected episode commitment during deal creation. The brand cannot choose or submit an arbitrary page to force bond slashing.
2.  **Parameterless Adjudication**: Once committed, `adjudicate_deal` audits strictly the pre-committed `deal.episode_url`. Neither party can pass an arbitrary URL during adjudication.
3.  **Semantic Evaluation**: Multiple independent validator nodes render the episode page, fetch the transcript, and prompt an LLM to evaluate if the creator met the talking points, read the sponsor script correctly, and mentioned the exact promo code/link.
4.  **Validator Agreement on MEANING**: The custom validator function (`validator_fn`) enforces consensus by requiring the nodes to agree on the semantic outcome (**Verdict**, **Payout Percentage**, and **Confidence Threshold >= 65%**), rather than just checking formatting.
5.  **Safe Challenge Step (No Instant Bond Slashing)**: If an AI audit returns `REJECTED`, the contract **does not immediately slash the creator's bond**. Instead, it transitions to a `CHALLENGED` status. This provides a safe challenge window where the platform arbiter verifies the outcome before any bond slashing occurs, completely preventing automated or malicious slashing.

---

## 🛠️ Public API

### Write Methods

*   **`create_deal(creator_addr: str, creator_channel_base: str, sponsor_script: str, required_promo_code: str) -> str`** *(Payable)*
    Allows a brand to create a deal by specifying the creator's address, the creator's official channel/domain base URL (e.g. `https://podcast.com/`), the required sponsor script, and the promo code. Sends the sponsorship budget as transaction value.
*   **`accept_and_stake(deal_id: str)`** *(Payable)*
    Allows the designated creator to accept the deal by staking a commitment bond (sent as transaction value).
*   **`commit_episode(deal_id: str, episode_url: str)`**
    **Creator-only**. Commits the exact published episode permalink. Must start with the registered `creator_channel_base`. Locks the deal into `COMMITTED` status.
*   **`adjudicate_deal(deal_id: str)`**
    Triggered by either party once the episode is committed. Audits the locked `deal.episode_url` without taking any external URL argument, preventing URL substitution.
*   **`submit_episode_and_adjudicate(deal_id: str, episode_url: str)`**
    Convenience method: Only the creator can invoke this to commit the exact episode and trigger adjudication in one transaction.
*   **`challenge_deal(deal_id: str, reason: str = "")`**
    Allows either party to raise a formal dispute on an audit outcome, moving the deal to `CHALLENGED` for arbiter review.
*   **`cancel_deal(deal_id: str)`**
    Allows the brand to cancel the deal and receive a 100% refund of their budget before the creator accepts and stakes.
*   **`resolve_escalated_deal(deal_id: str, creator_percentage: int)`**
    Allows the platform arbiter to manually resolve an `ESCALATED` or `CHALLENGED` deal. Setting `creator_percentage = 0` confirms the breach and slashes the creator bond to the brand. Any percentage > 0 distributes budget accordingly and returns the bond to the creator.

### View Methods

*   **`get_deal(deal_id: str) -> str`**
    Returns a JSON string containing the detailed state of a deal.
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
    *   `sponsor_script`: `"Support for this podcast comes from PodShield. Get 20% off your first subscription using code POD20 today."`
    *   `required_promo_code`: `"POD20"`
*   **Output**: `deal_id = "1"`

### 2. Deal Acceptance (Creator)
*   **Action**: Creator invokes `accept_and_stake("1")` and stakes `0.5 GEN` as a commitment bond.
*   **State transition**: Deal status changes from `OPEN` to `STAKED`.

### 3. Submission & Adjudication (Creator)
*   **Action**: Creator publishes the episode and invokes `submit_episode_and_adjudicate("1", "https://my-podcast-host.com/episodes/42")`.
*   **Execution**:
    *   The contract fetches the page content from `https://my-podcast-host.com/episodes/42` containing the transcript:
        `"...Thank you to our sponsor PodShield! Support for this podcast comes from PodShield. Get 20% off your first subscription using code POD20 today. Now back to the show..."`
    *   GenLayer AI consensus validates the ad-read. Both nodes agree on the verdict.
*   **Real Consensus Verdict (Audit Output)**:
    ```json
    {
      "verdict": "APPROVED",
      "payout_pct": 100,
      "confidence": 95,
      "reason": "The creator successfully read the full script and included the required promo code POD20."
    }
    ```
*   **Escrow Settlement (Deterministic)**:
    *   Creator Net Payout: `0.98 GEN` (100% budget minus 2% protocol fee).
    *   Treasury Fee: `0.02 GEN` (2% protocol fee).
    *   Bond Returned: `0.5 GEN` returned in full to the creator.
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
