# v0.2.16
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
from genlayer.gl.vm import UserError
from dataclasses import dataclass
import json


def _addr_str(addr: Address) -> str:
    try:
        return addr.as_hex.lower()
    except Exception:
        return str(addr).lower()


def _parse_llm_json(text) -> dict:
    if isinstance(text, dict):
        return text
    if hasattr(text, "content"):
        text = text.content
    try:
        cleaned = str(text).strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        return json.loads(cleaned.strip())
    except Exception as e:
        return {"verdict": "ABORT", "payout_pct": 0, "confidence": 0, "reason": f"Parse error: {str(e)}"}


def _evaluate(ep_url: str, script_target: str, promo_target: str) -> dict:
    try:
        res_ep = gl.nondet.web.render(ep_url, mode="text")
        ep_text = str(res_ep)
        if not ep_text or len(ep_text.strip()) < 30:
            return {"verdict": "ABORT", "payout_pct": 0, "confidence": 0, "reason": "Episode page returned empty content"}
        if any(err in ep_text[:400].lower() for err in ["404 not found", "error 404", "page not found"]):
            return {"verdict": "ABORT", "payout_pct": 0, "confidence": 0, "reason": "Episode page returned 404"}
    except Exception as e:
        return {"verdict": "ABORT", "payout_pct": 0, "confidence": 0, "reason": f"Web fetch failed: {str(e)}"}

    prompt = f"""
SYSTEM: You are a strict Media & Podcast Sponsorship Auditor.
Verify if the target episode content/transcript includes the sponsor ad-read and required promo code.

SPONSOR TALKING POINTS & SCRIPT:
{script_target}

REQUIRED PROMO CODE / LINK:
{promo_target}

EPISODE PAGE CONTENT / TRANSCRIPT:
{ep_text[:4000]}

Rules:
- APPROVED (payout_pct=100, conf >= 75): Ad-read covers all key talking points and includes the exact promo code/link.
- PARTIAL (payout_pct=1-99, conf >= 75): Ad-read is present but missed minor points or slightly altered the script.
- REJECTED (payout_pct=0, conf >= 75): No ad-read found, missing required promo code, or false delivery.
- ABORT: Content is rate-limited, captcha-blocked, audio player transcript inaccessible, or unreadable.

OUTPUT ONLY STRICT JSON:
{{
  "verdict": "APPROVED" | "PARTIAL" | "REJECTED" | "ABORT",
  "payout_pct": 0-100,
  "confidence": 0-100,
  "reason": "max 300 chars technical explanation"
}}
"""
    raw1 = gl.nondet.exec_prompt(prompt, response_format="json")
    raw2 = gl.nondet.exec_prompt(prompt, response_format="json")

    t1 = raw1.content if hasattr(raw1, "content") else raw1
    t2 = raw2.content if hasattr(raw2, "content") else raw2

    p1 = _parse_llm_json(t1)
    p2 = _parse_llm_json(t2)

    if p1.get("verdict") != p2.get("verdict"):
        return {"verdict": "ABORT", "payout_pct": 0, "confidence": 0, "reason": "multi_sample_divergence"}

    verdict = str(p1.get("verdict", "ABORT")).upper()
    if verdict not in ("APPROVED", "PARTIAL", "REJECTED", "ABORT"):
        verdict = "ABORT"

    pct = int(p1.get("payout_pct", 0))
    if verdict == "APPROVED":
        pct = 100
    elif verdict in ("REJECTED", "ABORT"):
        pct = 0
    elif verdict == "PARTIAL" and not (1 <= pct <= 99):
        verdict = "ABORT"
        pct = 0

    conf = (int(p1.get("confidence", 0)) + int(p2.get("confidence", 0))) // 2
    reason = str(p1.get("reason", ""))

    # Enforce strict confidence threshold
    if conf < 65 and verdict != "ABORT":
        verdict = "ABORT"
        pct = 0
        reason = f"[low_confidence: {conf}%] " + reason

    return {
        "verdict": verdict,
        "payout_pct": pct,
        "confidence": conf,
        "reason": reason[:300],
    }


@allow_storage
@dataclass
class SponsorshipDeal:
    id: str
    brand: str
    creator: str
    sponsor_script: str
    required_promo_code: str
    campaign_budget: bigint
    creator_bond: bigint
    episode_url: str
    status: str       # OPEN | STAKED | AUDITING | SETTLED | REFUNDED | ESCALATED
    verdict: str      # APPROVED | PARTIAL | REJECTED | ABORT
    payout_pct: bigint
    confidence: bigint
    reason: str


class Contract(gl.Contract):
    deals: TreeMap[str, SponsorshipDeal]
    deal_counter: bigint
    treasury_address: str
    total_locked_budget: bigint
    total_locked_bonds: bigint
    platform_arbiter: str

    def __init__(self, treasury_addr: str):
        self.deal_counter = bigint(0)
        treasury_addr = treasury_addr.strip() if treasury_addr else ""
        if not treasury_addr:
            raise UserError("Treasury address is required")
        try:
            # Validate address format during deployment
            Address(treasury_addr)
        except Exception:
            raise UserError("Invalid treasury address format")
        self.treasury_address = treasury_addr.lower()
        self.total_locked_budget = bigint(0)
        self.total_locked_bonds = bigint(0)
        self.platform_arbiter = _addr_str(gl.message.sender_address)

    def _treasury(self) -> Address:
        if not self.treasury_address:
            raise UserError("Treasury address is not configured")
        return Address(self.treasury_address)

    def _is_http(self, url: str) -> bool:
        u = url.strip().lower()
        return u.startswith("http://") or u.startswith("https://")

    @gl.public.write.payable
    def create_deal(
        self,
        creator_addr: str,
        sponsor_script: str,
        required_promo_code: str,
    ) -> str:
        """Brand creates a sponsorship deal and deposits payment into escrow."""
        budget = gl.message.value
        if budget <= bigint(0):
            raise UserError("Campaign budget must be greater than 0")

        creator_addr = creator_addr.strip()
        sponsor_script = sponsor_script.strip()
        required_promo_code = required_promo_code.strip()

        if not creator_addr:
            raise UserError("Creator address is required")
        try:
            # Validate address format
            creator_addr_validated = Address(creator_addr)
        except Exception:
            raise UserError("Invalid creator address format")
        
        creator_addr_normalized = creator_addr_validated.as_hex.lower()

        if len(sponsor_script) < 15:
            raise UserError("Sponsor script/key talking points too short")
        if len(required_promo_code) < 3:
            raise UserError("Promo code too short")

        self.deal_counter += bigint(1)
        deal_id = str(self.deal_counter)

        self.deals[deal_id] = SponsorshipDeal(
            id=deal_id,
            brand=_addr_str(gl.message.sender_address),
            creator=creator_addr_normalized,
            sponsor_script=sponsor_script,
            required_promo_code=required_promo_code,
            campaign_budget=budget,
            creator_bond=bigint(0),
            episode_url="",
            status="OPEN",
            verdict="",
            payout_pct=bigint(0),
            confidence=bigint(0),
            reason="",
        )
        self.total_locked_budget += budget
        return deal_id

    @gl.public.write.payable
    def accept_and_stake(self, deal_id: str) -> None:
        """Creator stakes a commitment bond to accept the ad placement deal."""
        if deal_id not in self.deals:
            raise UserError("Deal not found")
        deal = self.deals[deal_id]

        if _addr_str(gl.message.sender_address) != deal.creator.lower():
            raise UserError("Only the designated creator can accept this deal")
        if deal.status != "OPEN":
            raise UserError("Deal is not open for acceptance")

        bond = gl.message.value
        if bond <= bigint(0):
            raise UserError("Commitment bond must be greater than 0")

        deal.creator_bond = bond
        deal.status = "STAKED"
        self.deals[deal_id] = deal
        self.total_locked_bonds += bond

    @gl.public.write
    def cancel_deal(self, deal_id: str) -> None:
        """Brand can cancel and refund before creator stakes/accepts."""
        if deal_id not in self.deals:
            raise UserError("Deal not found")
        deal = self.deals[deal_id]

        if _addr_str(gl.message.sender_address) != deal.brand.lower():
            raise UserError("Only the brand can cancel")
        if deal.status != "OPEN":
            raise UserError("Can only cancel deals in OPEN status")

        deal.status = "REFUNDED"
        deal.verdict = "ABORT"
        deal.reason = "Cancelled by brand before creator acceptance"
        self.deals[deal_id] = deal

        refund_amt = deal.campaign_budget
        if self.total_locked_budget >= refund_amt:
            self.total_locked_budget -= refund_amt
        else:
            self.total_locked_budget = bigint(0)

        if refund_amt > bigint(0):
            gl.get_contract_at(Address(deal.brand)).emit_transfer(value=u256(refund_amt))

    @gl.public.write
    def submit_episode_and_adjudicate(
        self,
        deal_id: str,
        episode_url: str,
    ) -> None:
        """Creator submits public podcast/episode link, triggering autonomous AI consensus."""
        if deal_id not in self.deals:
            raise UserError("Deal not found")
        deal = self.deals[deal_id]

        if deal.status not in ("STAKED", "ESCALATED"):
            raise UserError("Deal is not ready for adjudication")

        sender = _addr_str(gl.message.sender_address)
        if sender != deal.creator.lower() and sender != deal.brand.lower():
            raise UserError("Only creator or brand can trigger adjudication")

        episode_url = episode_url.strip()
        if not self._is_http(episode_url):
            raise UserError("episode_url must start with http(s)://")

        deal.episode_url = episode_url
        deal.status = "AUDITING"
        self.deals[deal_id] = deal

        script_target = str(deal.sponsor_script)
        promo_target = str(deal.required_promo_code)
        ep_url = str(episode_url)

        def leader_fn():
            return _evaluate(ep_url, script_target, promo_target)

        def validator_fn(leader_res) -> bool:
            if not isinstance(leader_res, gl.vm.Return):
                return False

            leader_data = leader_res.calldata if hasattr(leader_res, "calldata") else leader_res
            if not isinstance(leader_data, dict):
                leader_data = _parse_llm_json(leader_data)

            mine_data = _evaluate(ep_url, script_target, promo_target)

            l_verdict = str(leader_data.get("verdict", "ABORT")).upper()
            m_verdict = str(mine_data.get("verdict", "ABORT")).upper()
            l_pct = int(leader_data.get("payout_pct", 0))
            m_pct = int(mine_data.get("payout_pct", 0))

            return (l_verdict == m_verdict) and (l_pct == m_pct)

        result = gl.vm.run_nondet(leader_fn, validator_fn)
        if not isinstance(result, dict):
            result = _parse_llm_json(result)

        verdict = str(result.get("verdict", "ABORT")).upper()
        if verdict not in ("APPROVED", "PARTIAL", "REJECTED", "ABORT"):
            verdict = "ABORT"

        payout_pct = int(result.get("payout_pct", 0))
        confidence = int(result.get("confidence", 0))
        reason = str(result.get("reason", "Media ad-placement consensus completed"))

        # Post-consensus deterministic normalization
        if confidence < 65 and verdict != "ABORT":
            verdict = "ABORT"
            payout_pct = 0

        deal.verdict = verdict
        deal.payout_pct = bigint(payout_pct)
        deal.confidence = bigint(confidence)
        deal.reason = reason

        budget_amt = deal.campaign_budget
        bond_amt = deal.creator_bond
        creator_addr = Address(deal.creator)
        brand_addr = Address(deal.brand)

        if verdict in ("APPROVED", "PARTIAL"):
            payout = (budget_amt * bigint(payout_pct)) // bigint(100)
            refund_to_brand = budget_amt - payout

            # 2% protocol fee on creator payout
            fee = (payout * bigint(2)) // bigint(100)
            creator_net = payout - fee

            if fee > bigint(0):
                gl.get_contract_at(self._treasury()).emit_transfer(value=u256(fee))
            # Creator receives earned budget share + 100% bond return
            if creator_net + bond_amt > bigint(0):
                gl.get_contract_at(creator_addr).emit_transfer(value=u256(creator_net + bond_amt))
            if refund_to_brand > bigint(0):
                gl.get_contract_at(brand_addr).emit_transfer(value=u256(refund_to_brand))

            deal.status = "SETTLED"
            if self.total_locked_budget >= budget_amt:
                self.total_locked_budget -= budget_amt
            else:
                self.total_locked_budget = bigint(0)

            if self.total_locked_bonds >= bond_amt:
                self.total_locked_bonds -= bond_amt
            else:
                self.total_locked_bonds = bigint(0)

        elif verdict == "REJECTED":
            # Failed ad delivery: Brand gets 100% budget refund + slashed creator bond as damages
            gl.get_contract_at(brand_addr).emit_transfer(value=u256(budget_amt + bond_amt))
            deal.status = "SETTLED"

            if self.total_locked_budget >= budget_amt:
                self.total_locked_budget -= budget_amt
            else:
                self.total_locked_budget = bigint(0)

            if self.total_locked_bonds >= bond_amt:
                self.total_locked_bonds -= bond_amt
            else:
                self.total_locked_bonds = bigint(0)

        else:
            # ABORT: Network/render issue, escalate safely for retry without moving funds
            deal.status = "ESCALATED"

        self.deals[deal_id] = deal

    @gl.public.write
    def resolve_escalated_deal(
        self,
        deal_id: str,
        creator_percentage: int,
    ) -> None:
        """Platform Arbiter manually resolves an ESCALATED deal."""
        if deal_id not in self.deals:
            raise UserError("Deal not found")
        deal = self.deals[deal_id]

        if deal.status != "ESCALATED":
            raise UserError("Deal is not in ESCALATED status")

        sender = _addr_str(gl.message.sender_address)
        if sender != self.platform_arbiter:
            raise UserError("Only platform arbiter can resolve escalated deals")

        if not (0 <= creator_percentage <= 100):
            raise UserError("creator_percentage must be between 0 and 100")

        budget_amt = deal.campaign_budget
        bond_amt = deal.creator_bond
        creator_addr = Address(deal.creator)
        brand_addr = Address(deal.brand)

        payout = (budget_amt * bigint(creator_percentage)) // bigint(100)
        refund_to_brand = budget_amt - payout

        fee = (payout * bigint(2)) // bigint(100)
        creator_net = payout - fee

        if fee > bigint(0):
            gl.get_contract_at(self._treasury()).emit_transfer(value=u256(fee))
        if creator_net + bond_amt > bigint(0):
            gl.get_contract_at(creator_addr).emit_transfer(value=u256(creator_net + bond_amt))
        if refund_to_brand > bigint(0):
            gl.get_contract_at(brand_addr).emit_transfer(value=u256(refund_to_brand))

        deal.status = "SETTLED"
        deal.verdict = f"RESOLVED_MANUALLY_{creator_percentage}_PERCENT"
        deal.reason = f"Manually settled by arbiter ({sender})"
        self.deals[deal_id] = deal

        if self.total_locked_budget >= budget_amt:
            self.total_locked_budget -= budget_amt
        else:
            self.total_locked_budget = bigint(0)

        if self.total_locked_bonds >= bond_amt:
            self.total_locked_bonds -= bond_amt
        else:
            self.total_locked_bonds = bigint(0)

    @gl.public.view
    def get_deal(self, deal_id: str) -> str:
        if deal_id not in self.deals:
            raise UserError("Deal not found")
        d = self.deals[deal_id]
        return json.dumps({
            "id": d.id,
            "brand": d.brand,
            "creator": d.creator,
            "sponsor_script": d.sponsor_script,
            "required_promo_code": d.required_promo_code,
            "campaign_budget": str(d.campaign_budget),
            "creator_bond": str(d.creator_bond),
            "episode_url": d.episode_url,
            "status": d.status,
            "verdict": d.verdict,
            "payout_pct": str(d.payout_pct),
            "confidence": str(d.confidence),
            "reason": d.reason,
        })

    @gl.public.view
    def get_deal_counter(self) -> int:
        return int(self.deal_counter)

    @gl.public.view
    def get_treasury(self) -> str:
        return self.treasury_address
