# Security Audit Finding Report: 2025-07-oku-trade-order-types
- **Platform Target:** Local
- **Audit Date:** 2026-09-02 15:41:05
- **Total High/Medium Findings:** 4

---

## [H-01] Contract locks Ether without a withdraw function
- **Severity:** High
- **Target Contract:** `2025-07-oku-trade-order-types` (`oku-custom-order-types/contracts/oracle/External/PythOracle.sol`)
- **Line Range:** `L7-L7`
- **PoC Status:** ⚠️ Semantic Analysis

### 1. Impact Summary
Discovered by aderyn [contract-locks-ether]. Potential High impact on contract state/funds.

### 2. Vulnerability Detail & Root Cause
It appears that the contract includes a payable function to accept Ether but lacks a corresponding function to withdraw it, which leads to the Ether being locked in the contract. To resolve this issue, please implement a public or external function that allows for the withdrawal of Ether from the contract.

### 3. Step-by-Step Exploit Scenario
1. An attacker identifies state inconsistency at `oku-custom-order-types/contracts/oracle/External/PythOracle.sol:L7-L7`.
2. By executing crafted transactions targeting `2025-07-oku-trade-order-types`, protocol assumptions are violated.
3. Unintended asset transfer or privilege escalation occurs.

### 5. Recommended Mitigation Steps
Introduce explicit boundary validation, require checks, and appropriate role-based access modifiers.

---

## [H-02] ETH transferred without address checks
- **Severity:** High
- **Target Contract:** `2025-07-oku-trade-order-types` (`oku-custom-order-types/contracts/automatedTrigger/Bracket.sol`)
- **Line Range:** `L143-L143`
- **PoC Status:** ⚠️ Semantic Analysis

### 1. Impact Summary
Discovered by aderyn [eth-send-unchecked-address]. Potential High impact on contract state/funds.

### 2. Vulnerability Detail & Root Cause
Consider introducing checks for `msg.sender` to ensure the recipient of the money is as intended.

### 3. Step-by-Step Exploit Scenario
1. An attacker identifies state inconsistency at `oku-custom-order-types/contracts/automatedTrigger/Bracket.sol:L143-L143`.
2. By executing crafted transactions targeting `2025-07-oku-trade-order-types`, protocol assumptions are violated.
3. Unintended asset transfer or privilege escalation occurs.

### 5. Recommended Mitigation Steps
Introduce explicit boundary validation, require checks, and appropriate role-based access modifiers.

---

## [H-03] Reentrancy: State change after external call
- **Severity:** High
- **Target Contract:** `2025-07-oku-trade-order-types` (`oku-custom-order-types/contracts/automatedTrigger/Bracket.sol`)
- **Line Range:** `L315-L315`
- **PoC Status:** ⚠️ Semantic Analysis

### 1. Impact Summary
Discovered by aderyn [reentrancy-state-change]. Potential High impact on contract state/funds.

### 2. Vulnerability Detail & Root Cause
Changing state after an external call can lead to re-entrancy attacks.Use the checks-effects-interactions pattern to avoid this issue.

### 3. Step-by-Step Exploit Scenario
1. Attacker invokes target function in `2025-07-oku-trade-order-types`.
2. An external call transfers control to attacker's contract before state variables are fully updated.
3. Attacker contract re-enters the victim function repeatedly before balance/state decrements occur, draining protocol reserves.

### 5. Recommended Mitigation Steps
Apply OpenZeppelin's `ReentrancyGuard` with `nonReentrant` modifier and enforce the Checks-Effects-Interactions (CEI) pattern.

---

## [H-04] Unsafe Casting of integers
- **Severity:** High
- **Target Contract:** `2025-07-oku-trade-order-types` (`oku-custom-order-types/contracts/automatedTrigger/AutomationMaster.sol`)
- **Line Range:** `L224-L224`
- **PoC Status:** ⚠️ Semantic Analysis

### 1. Impact Summary
Discovered by aderyn [unsafe-casting]. Potential High impact on contract state/funds.

### 2. Vulnerability Detail & Root Cause
Downcasting int/uints in Solidity can be unsafe due to the potential for data loss and unintended behavior.When downcasting a larger integer type to a smaller one (e.g., uint256 to uint128), the value may exceed the range of the target type,leading to truncation and loss of significant digits. Use OpenZeppelin's SafeCast library to safely downcast integers.

### 3. Step-by-Step Exploit Scenario
1. Attacker provides input exceeding the maximum bit-width capacity of the downcasted type in `oku-custom-order-types/contracts/automatedTrigger/AutomationMaster.sol` at L224-L224.
2. Integer downcasting silently truncates the upper bits without reverting.
3. Corrupted numerical state leads to incorrect fee calculation or undercollateralized loans.

### 5. Recommended Mitigation Steps
Use OpenZeppelin's `SafeCast` library (e.g. `SafeCast.toUint128(...)`) to revert automatically on overflow.

---
