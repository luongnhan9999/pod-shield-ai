import json
from tests.direct.conftest import to_hex

def _setup_adjudicate_mocks(vm, episode_url, body_content, llm_verdict, payout_pct, confidence, reason="Consensus audit completed"):
    """Register web rendering and LLM mocks for adjudication."""
    vm.mock_web(
        rf".*{episode_url}.*",
        {"status": 200, "body": body_content},
    )
    
    # The prompt regex matches the system prompt for Media & Podcast Sponsorship Auditor
    prompt_pattern = r".*SYSTEM: You are a strict Media & Podcast Sponsorship Auditor.*"
    
    # The contract makes two LLM calls for multi-sample validation.
    # We will mock the response for the prompt.
    llm_resp = json.dumps({
        "verdict": llm_verdict,
        "payout_pct": payout_pct,
        "confidence": confidence,
        "reason": reason
    })
    vm.mock_llm(prompt_pattern, llm_resp)


def test_create_deal(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    # Deploy contract with Charlie as treasury
    treasury = to_hex(direct_charlie)
    contract = direct_deploy("contracts/pod_shield.py", treasury)
    
    # Alice (brand) creates a deal for Bob (creator)
    direct_vm.sender = direct_alice
    direct_vm.value = 1000  # Send 1000 wei budget
    
    deal_id = contract.create_deal(
        to_hex(direct_bob),
        "This is the sponsor script that is longer than fifteen characters",
        "PROMO123"
    )
    
    # Reset VM value
    direct_vm.value = 0
    
    assert deal_id == "1"
    assert contract.get_deal_counter() == 1
    assert contract.get_treasury() == treasury.lower()
    
    deal_info = json.loads(contract.get_deal(deal_id))
    assert deal_info["id"] == "1"
    assert deal_info["brand"] == to_hex(direct_alice).lower()
    assert deal_info["creator"] == to_hex(direct_bob).lower()
    assert deal_info["campaign_budget"] == "1000"
    assert deal_info["creator_bond"] == "0"
    assert deal_info["status"] == "OPEN"


def test_accept_and_stake(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    contract = direct_deploy("contracts/pod_shield.py", to_hex(direct_charlie))
    
    # Alice creates deal
    direct_vm.sender = direct_alice
    direct_vm.value = 1000
    deal_id = contract.create_deal(
        to_hex(direct_bob),
        "This is the sponsor script that is longer than fifteen characters",
        "PROMO123"
    )
    direct_vm.value = 0
    
    # Bob (creator) accepts and stakes
    direct_vm.sender = direct_bob
    direct_vm.value = 500  # Staking 500 wei bond
    contract.accept_and_stake(deal_id)
    direct_vm.value = 0
    
    deal_info = json.loads(contract.get_deal(deal_id))
    assert deal_info["status"] == "STAKED"
    assert deal_info["creator_bond"] == "500"


def test_cancel_deal(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    contract = direct_deploy("contracts/pod_shield.py", to_hex(direct_charlie))
    
    direct_vm.sender = direct_alice
    direct_vm.value = 1000
    deal_id = contract.create_deal(
        to_hex(direct_bob),
        "This is the sponsor script that is longer than fifteen characters",
        "PROMO123"
    )
    direct_vm.value = 0
    
    # Cancel by brand
    direct_vm.sender = direct_alice
    contract.cancel_deal(deal_id)
    
    deal_info = json.loads(contract.get_deal(deal_id))
    assert deal_info["status"] == "REFUNDED"
    assert deal_info["verdict"] == "ABORT"


def test_adjudicate_approved(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    contract = direct_deploy("contracts/pod_shield.py", to_hex(direct_charlie))
    
    # 1. Create deal
    direct_vm.sender = direct_alice
    direct_vm.value = 1000
    deal_id = contract.create_deal(
        to_hex(direct_bob),
        "This is the sponsor script that is longer than fifteen characters",
        "PROMO123"
    )
    direct_vm.value = 0
    
    # 2. Stake
    direct_vm.sender = direct_bob
    direct_vm.value = 500
    contract.accept_and_stake(deal_id)
    direct_vm.value = 0
    
    # 3. Adjudicate (mocking LLM as APPROVED)
    episode_url = "https://example.com/episode1"
    body_content = "This transcript contains sponsor script that is longer than fifteen characters and the promo code PROMO123"
    _setup_adjudicate_mocks(
        direct_vm,
        "example.com/episode1",
        body_content,
        "APPROVED",
        100,
        90
    )
    
    direct_vm.sender = direct_bob
    contract.submit_episode_and_adjudicate(deal_id, episode_url)
    
    deal_info = json.loads(contract.get_deal(deal_id))
    assert deal_info["status"] == "SETTLED"
    assert deal_info["verdict"] == "APPROVED"
    assert deal_info["payout_pct"] == "100"


def test_adjudicate_partial(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    contract = direct_deploy("contracts/pod_shield.py", to_hex(direct_charlie))
    
    # Create and stake
    direct_vm.sender = direct_alice
    direct_vm.value = 1000
    deal_id = contract.create_deal(
        to_hex(direct_bob),
        "This is the sponsor script that is longer than fifteen characters",
        "PROMO123"
    )
    direct_vm.value = 0
    
    direct_vm.sender = direct_bob
    direct_vm.value = 500
    contract.accept_and_stake(deal_id)
    direct_vm.value = 0
    
    # Adjudicate (mocking LLM as PARTIAL payout 75%)
    episode_url = "https://example.com/episode2"
    body_content = "This is a transcript where the creator mentions most of the sponsor script but changes a small part, uses promo PROMO123"
    _setup_adjudicate_mocks(
        direct_vm,
        "example.com/episode2",
        body_content,
        "PARTIAL",
        75,
        80
    )
    
    direct_vm.sender = direct_bob
    contract.submit_episode_and_adjudicate(deal_id, episode_url)
    
    deal_info = json.loads(contract.get_deal(deal_id))
    assert deal_info["status"] == "SETTLED"
    assert deal_info["verdict"] == "PARTIAL"
    assert deal_info["payout_pct"] == "75"


def test_adjudicate_rejected(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    contract = direct_deploy("contracts/pod_shield.py", to_hex(direct_charlie))
    
    # Create and stake
    direct_vm.sender = direct_alice
    direct_vm.value = 1000
    deal_id = contract.create_deal(
        to_hex(direct_bob),
        "This is the sponsor script that is longer than fifteen characters",
        "PROMO123"
    )
    direct_vm.value = 0
    
    direct_vm.sender = direct_bob
    direct_vm.value = 500
    contract.accept_and_stake(deal_id)
    direct_vm.value = 0
    
    # Adjudicate (mocking LLM as REJECTED)
    episode_url = "https://example.com/episode3"
    body_content = "This transcript does not mention anything related to the sponsor and does not contain the promo code."
    _setup_adjudicate_mocks(
        direct_vm,
        "example.com/episode3",
        body_content,
        "REJECTED",
        0,
        95
    )
    
    direct_vm.sender = direct_bob
    contract.submit_episode_and_adjudicate(deal_id, episode_url)
    
    deal_info = json.loads(contract.get_deal(deal_id))
    assert deal_info["status"] == "SETTLED"
    assert deal_info["verdict"] == "REJECTED"
    assert deal_info["payout_pct"] == "0"


def test_adjudicate_escalated_and_resolved(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    # Deploy contract by Alice (so Alice is the platform arbiter)
    direct_vm.sender = direct_alice
    contract = direct_deploy("contracts/pod_shield.py", to_hex(direct_charlie))
    
    # Create and stake
    direct_vm.sender = direct_alice
    direct_vm.value = 1000
    deal_id = contract.create_deal(
        to_hex(direct_bob),
        "This is the sponsor script that is longer than fifteen characters",
        "PROMO123"
    )
    direct_vm.value = 0
    
    direct_vm.sender = direct_bob
    direct_vm.value = 500
    contract.accept_and_stake(deal_id)
    direct_vm.value = 0
    
    # Adjudicate (mocking LLM as ABORT due to failure/divergence)
    episode_url = "https://example.com/episode4"
    body_content = "Some page content"
    _setup_adjudicate_mocks(
        direct_vm,
        "example.com/episode4",
        body_content,
        "ABORT",
        0,
        0
    )
    
    direct_vm.sender = direct_bob
    contract.submit_episode_and_adjudicate(deal_id, episode_url)
    
    deal_info = json.loads(contract.get_deal(deal_id))
    assert deal_info["status"] == "ESCALATED"
    
    # Settle manually by the arbiter (Alice)
    direct_vm.sender = direct_alice
    contract.resolve_escalated_deal(deal_id, 40)
    
    deal_info = json.loads(contract.get_deal(deal_id))
    assert deal_info["status"] == "SETTLED"
    assert deal_info["verdict"] == "RESOLVED_MANUALLY_40_PERCENT"
