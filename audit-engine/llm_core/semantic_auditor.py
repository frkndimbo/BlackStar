import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from config import config
from analyzers.static_engine import StaticFinding

logger = logging.getLogger("SemanticAuditor")


class VerifiedVulnerability(BaseModel):
    title: str
    severity: str  # High, Medium, Low
    contract_name: str
    file_path: str
    line_range: str
    impact_summary: str
    detailed_path: str
    exploit_scenario: str
    recommended_mitigation: str
    poc_solidity_code: Optional[str] = ""
    is_poc_verified: bool = False
    false_positive_reason: Optional[str] = ""


class SemanticAuditor:
    def __init__(self):
        self.gemini_client = None
        self.openai_client = None

        # 1. Initialize Google GenAI if key available
        if config.gemini_api_key:
            try:
                from google import genai
                self.gemini_client = genai.Client(api_key=config.gemini_api_key)
                logger.info(f"Google Gemini GenAI client initialized with model: {config.gemini_model_flash}")
            except Exception as e:
                logger.warning(f"Could not initialize Google GenAI client: {e}")

        # 2. Initialize OpenAI fallback if available
        if not self.gemini_client and config.openai_api_key:
            try:
                from openai import OpenAI
                self.openai_client = OpenAI(api_key=config.openai_api_key)
                logger.info("OpenAI client initialized as fallback for SemanticAuditor.")
            except Exception as e:
                logger.warning(f"Could not initialize OpenAI client: {e}")

    def extract_key_contracts(self, repo_path: Path, max_files: int = 25) -> Dict[str, str]:
        """Find core contract files (.sol) excluding tests, mocks, interfaces, and build artifacts."""
        contracts = {}
        for sol_file in sorted(repo_path.glob("**/*.sol")):
            if not sol_file.is_file():
                continue
            rel_path = str(sol_file.relative_to(repo_path))
            lower_rel = rel_path.lower()
            if any(x in lower_rel for x in [
                "test", "tests", "mock", "mocks", "script", "scripts",
                "node_modules", "lib", "out", "artifacts", "build", "forge-std"
            ]):
                continue

            try:
                with open(sol_file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    lines = content.splitlines()
                    if len(lines) > 25 and ("contract " in content or "abstract contract " in content):
                        contracts[rel_path] = content
            except Exception as e:
                logger.warning(f"Could not read {sol_file}: {e}")

            if len(contracts) >= max_files:
                break

        return contracts

    def query_llm(self, prompt: str, system_instruction: str = "", model_tier: str = "flash") -> Optional[str]:
        """Query LLM (Gemini or OpenAI) with system prompt."""
        # 1. Try Gemini
        if self.gemini_client:
            try:
                model_name = config.gemini_model_pro if model_tier == "pro" else config.gemini_model_flash
                response = self.gemini_client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={
                        "system_instruction": system_instruction,
                        "temperature": 0.2,
                    }
                )
                return response.text
            except Exception as e:
                logger.warning(f"Gemini API error: {e}")

        # 2. Try OpenAI
        if self.openai_client:
            try:
                model_name = "gpt-4o" if model_tier == "pro" else "gpt-4o-mini"
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                messages.append({"role": "user", "content": prompt})

                response = self.openai_client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=0.2
                )
                return response.choices[0].message.content
            except Exception as e:
                logger.warning(f"OpenAI API error: {e}")

        return None

    def verify_and_filter_findings(
        self,
        repo_path: Path,
        static_findings: List[StaticFinding],
        contracts: Dict[str, str]
    ) -> List[VerifiedVulnerability]:
        """
        Takes raw static scanner findings and verifies each against actual contract code.
        Prunes false positives and generates rigorous vulnerability reports for true issues.
        """
        verified_list: List[VerifiedVulnerability] = []

        for idx, finding in enumerate(static_findings):
            loc = finding.locations[0] if finding.locations else None
            file_p = loc.file_path if loc else "contracts"
            line_r = f"L{loc.start_line}-L{loc.end_line}" if loc else "L1"
            contract_name = loc.contract_name if loc and loc.contract_name else repo_path.name

            # Retrieve file source code if available
            contract_code = ""
            for cp, code in contracts.items():
                if file_p in cp or cp in file_p:
                    contract_code = code
                    break

            # Check for deterministic false positives first
            is_fp, fp_reason = self._deterministic_false_positive_check(finding, contract_code, loc)
            if is_fp:
                logger.info(f"🚫 Pruned False Positive [{finding.detector}] in {file_p}:{line_r} -> Reason: {fp_reason}")
                continue

            # If LLM is available, perform deep LLM verification & exploit synthesis
            llm_result = None
            if self.gemini_client or self.openai_client:
                llm_result = self._llm_verify_finding(finding, file_p, line_r, contract_name, contract_code)

            if llm_result:
                if llm_result.get("is_valid", False):
                    vuln = VerifiedVulnerability(
                        title=llm_result.get("title", finding.title),
                        severity=llm_result.get("severity", finding.severity),
                        contract_name=contract_name,
                        file_path=file_p,
                        line_range=line_r,
                        impact_summary=llm_result.get("impact_summary", finding.description),
                        detailed_path=llm_result.get("root_cause", finding.description),
                        exploit_scenario=llm_result.get("exploit_scenario", ""),
                        recommended_mitigation=llm_result.get("mitigation", ""),
                        poc_solidity_code=llm_result.get("poc_code", ""),
                        is_poc_verified=False
                    )
                    verified_list.append(vuln)
                else:
                    logger.info(f"🚫 LLM pruned false positive [{finding.detector}] in {file_p}:{line_r}: {llm_result.get('reason', '')}")
            else:
                # Heuristic fallback when LLM is unavailable
                vuln = self._heuristic_vulnerability_builder(finding, file_p, line_r, contract_name, contract_code)
                if vuln:
                    verified_list.append(vuln)

        return verified_list

    def _deterministic_false_positive_check(
        self,
        finding: StaticFinding,
        contract_code: str,
        loc: Any
    ) -> tuple[bool, str]:
        """Rule-based verification to immediately prune known static analyzer false positives."""
        if not contract_code:
            return False, ""

        # 1. Arbitrary-send-erc20 false positive check:
        # If transferFrom(sender, ...) is called where sender is protected by onlySender/onlyOwner/msg.sender
        if finding.detector == "arbitrary-send-erc20":
            if "onlySUSDM" in contract_code or "onlyOwner" in contract_code or "onlyRole" in contract_code:
                if "msg.sender !=" in contract_code and "revert" in contract_code:
                    return True, "Call is guarded by strict access control modifier matching sender address."

        # 2. Reentrancy on view functions or balanceOf checks:
        if finding.detector in ["reentrancy-state-change", "reentrancy-balance", "reentrancy-no-eth"]:
            if "balanceOf(" in finding.description and ("totalWithdrawn +=" in contract_code or "totalDeposited +=" in contract_code):
                if "safeTransfer(" in contract_code and "nonReentrant" in contract_code:
                    return True, "Contract uses nonReentrant guard and standard Checks-Effects-Interactions pattern."

        # 3. Contract locks ether false positive (when contract has no payable receive or fallback, or is abstract)
        if finding.detector == "contract-locks-ether":
            if "receive()" not in contract_code and "fallback()" not in contract_code and "payable" not in contract_code:
                return True, "Contract contains no payable functions and cannot accept or lock native ETH."

        # 4. Unsafe casting when casting is bounded by require or constants
        if finding.detector == "unsafe-casting":
            if "require(" in contract_code and ("<= type(uint128).max" in contract_code or "<= 1e" in contract_code):
                return True, "Cast value is explicitly validated with boundary require checks."

        return False, ""

    def _llm_verify_finding(
        self,
        finding: StaticFinding,
        file_path: str,
        line_range: str,
        contract_name: str,
        contract_code: str
    ) -> Optional[dict]:
        """Use LLM to assess validity, root cause, and synthesize exact exploit steps."""
        system_prompt = (
            "You are a Principal Smart Contract Security Auditor for Code4rena and Sherlock. "
            "Evaluate whether the static analysis finding is a REAL high/medium security vulnerability or a FALSE POSITIVE. "
            "Return JSON only with keys: is_valid (bool), reason (str), title (str), severity (High/Medium/Low), "
            "impact_summary (str), root_cause (str), exploit_scenario (str), mitigation (str), poc_code (str)."
        )

        user_prompt = f"""
Audit Finding to Validate:
- Detector: {finding.detector} (Source: {finding.source_tool})
- Severity Signal: {finding.severity}
- File: {file_path} ({line_range})
- Target Contract: {contract_name}
- Raw Description: {finding.description}

Target Contract Source Code Excerpt:
```solidity
{contract_code[:4000]}
```

Provide strict evaluation. If this is a false positive due to modifier access controls, reentrancy guards, or safe design, set is_valid to false.
Output valid JSON only.
"""
        raw_resp = self.query_llm(user_prompt, system_instruction=system_prompt, model_tier="flash")
        if not raw_resp:
            return None

        try:
            cleaned = raw_resp.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()
            return json.loads(cleaned)
        except Exception as e:
            logger.warning(f"Failed to parse LLM verification JSON: {e}")
            return None

    def _heuristic_vulnerability_builder(
        self,
        finding: StaticFinding,
        file_path: str,
        line_range: str,
        contract_name: str,
        contract_code: str
    ) -> VerifiedVulnerability:
        """Constructs an accurate finding report with precise technical remediation."""
        detector = finding.detector
        title = finding.title

        if detector == "arbitrary-send-erc20":
            exploit = (
                f"1. Attacker calls `{contract_name}` function at {file_path}:{line_range}.\n"
                f"2. Because the transfer uses arbitrary `from` parameter without checking allowance or caller equality, funds may be pulled from victim accounts.\n"
                f"3. Attacker directs transferred tokens to their own controlled address."
            )
            mitigation = "Ensure `msg.sender` is strictly verified as the owner of the source tokens or enforce proper allowance validation."
        elif "reentrancy" in detector:
            exploit = (
                f"1. Attacker invokes target function in `{contract_name}`.\n"
                f"2. An external call transfers control to attacker's contract before state variables are fully updated.\n"
                f"3. Attacker contract re-enters the victim function repeatedly before balance/state decrements occur, draining protocol reserves."
            )
            mitigation = "Apply OpenZeppelin's `ReentrancyGuard` with `nonReentrant` modifier and enforce the Checks-Effects-Interactions (CEI) pattern."
        elif detector == "unsafe-casting":
            exploit = (
                f"1. Attacker provides input exceeding the maximum bit-width capacity of the downcasted type in `{file_path}` at {line_range}.\n"
                f"2. Integer downcasting silently truncates the upper bits without reverting.\n"
                f"3. Corrupted numerical state leads to incorrect fee calculation or undercollateralized loans."
            )
            mitigation = "Use OpenZeppelin's `SafeCast` library (e.g. `SafeCast.toUint128(...)`) to revert automatically on overflow."
        else:
            exploit = (
                f"1. An attacker identifies state inconsistency at `{file_path}:{line_range}`.\n"
                f"2. By executing crafted transactions targeting `{contract_name}`, protocol assumptions are violated.\n"
                f"3. Unintended asset transfer or privilege escalation occurs."
            )
            mitigation = "Introduce explicit boundary validation, require checks, and appropriate role-based access modifiers."

        return VerifiedVulnerability(
            title=title,
            severity=finding.severity,
            contract_name=contract_name,
            file_path=file_path,
            line_range=line_r if (line_r := line_range) else "L1",
            impact_summary=f"Discovered by {finding.source_tool} [{detector}]. Potential {finding.severity} impact on contract state/funds.",
            detailed_path=finding.description,
            exploit_scenario=exploit,
            recommended_mitigation=mitigation,
            is_poc_verified=False
        )

    def deep_semantic_logic_audit(self, repo_path: Path) -> List[VerifiedVulnerability]:
        """Performs deep cross-contract logic audit using Gemini/OpenAI."""
        contracts = self.extract_key_contracts(repo_path, max_files=15)
        if not contracts:
            return []

        if not (self.gemini_client or self.openai_client):
            logger.info("Skipping deep LLM semantic audit because no LLM API key is configured.")
            return []

        logger.info(f"🧠 Executing deep LLM semantic audit on {len(contracts)} core contracts in {repo_path.name}...")
        
        system_prompt = (
            "You are a World-Class Smart Contract Security Auditor on Code4rena and Sherlock. "
            "Audit the given Solidity codebase for HIGH and MEDIUM severity business logic bugs: "
            "1. Flash loan attacks & Oracle price manipulation\n"
            "2. Precision loss / rounding errors in fee/reward distribution\n"
            "3. Read-only reentrancy across view functions during state updates\n"
            "4. Missing access control or uninitialized proxy implementation\n"
            "5. Invariant violations in deposit, borrow, liquidate, or redeem flows\n\n"
            "Only return REAL, actionable vulnerabilities. Return a JSON array of findings with keys: "
            "title, severity (High/Medium), contract_name, file_path, line_range, impact_summary, root_cause, exploit_scenario, mitigation, poc_code."
        )

        contracts_summary = ""
        for p, code in list(contracts.items())[:8]:
            contracts_summary += f"\nFile: `{p}`\n```solidity\n{code[:3000]}\n```\n"

        user_prompt = f"Audit the following smart contracts in repo {repo_path.name}:\n{contracts_summary}\nOutput JSON array only."

        resp = self.query_llm(user_prompt, system_instruction=system_prompt, model_tier="pro")
        if not resp:
            return []

        try:
            cleaned = resp.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()
            
            items = json.loads(cleaned)
            findings = []
            for it in items:
                findings.append(VerifiedVulnerability(
                    title=it.get("title", "Logic Invariant Violation"),
                    severity=it.get("severity", "High"),
                    contract_name=it.get("contract_name", repo_path.name),
                    file_path=it.get("file_path", "contracts"),
                    line_range=it.get("line_range", "L1"),
                    impact_summary=it.get("impact_summary", ""),
                    detailed_path=it.get("root_cause", ""),
                    exploit_scenario=it.get("exploit_scenario", ""),
                    recommended_mitigation=it.get("mitigation", ""),
                    poc_solidity_code=it.get("poc_code", ""),
                    is_poc_verified=False
                ))
            return findings
        except Exception as e:
            logger.warning(f"Failed to parse deep logic audit response: {e}")
            return []

