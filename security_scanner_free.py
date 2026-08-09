#!/usr/bin/env python3


import os
import re
import ast
import zipfile
import tarfile
import tempfile
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PATTERNS: Dict[str, List[Tuple[str, str]]] = {

    # ── Real data theft ─────────────────────────────────────────
    "🔴 Data Theft": [
        (r'os\.walk\s*\(\s*["\'][/\\](?:root|home|etc|var|proc)["\']',
            "os.walk server directory — server files chura raha hai"),
        (r'send_document\s*\([^\n]*open\s*\(\s*["\'][/\\](?:root|etc|proc|sys)',
            "System file Telegram pe bhej raha hai"),
        (r'glob\.glob\s*\(\s*["\'][/\\]\*',
            "Root se glob scan — server files dhundh raha hai"),
        (r'shutil\.(?:copy|copy2|copyfile)\s*\([^\n]*/root',
            "/root se copy kar raha hai"),
        (r'ROOT_DIR\s*=\s*["\'][/\\]["\']',
            "Root directory target kar raha hai"),
        (r'\bbackup_log\b',
            "backup_log — data theft disguise ho sakta hai"),
        (r'arcname\s*=\s*os\.path\.relpath',
            "Files ko relative path se ZIP mein pack kar raha hai"),
        (r'post_init\s*=.*send_document|send_document.*post_init',
            "Startup pe file auto-send — suspicious"),
    ],

    # ── Hidden / nested bots ─────────────────────────────────────
    "🟠 Hidden Bot": [
        (r'\binfinity_polling\s*\(',
            "infinity_polling — dusra bot chal raha hai (normal for hosted bots)"),
        (r'\brun_polling\s*\(',
            "run_polling — dusra bot (normal for hosted bots)"),
        (r'\bbot\.polling\s*\(',
            "bot.polling — bot chal raha hai"),
        (r'\bupdater\.start_polling\s*\(',
            "updater.start_polling — v13 style bot"),
        (r'Application\.builder\s*\(\s*\)',
            "Application.builder() — python-telegram-bot v20"),
        (r'\btelebot\.TeleBot\s*\(',
            "telebot.TeleBot() — bot instance"),
        (r'\bBot\s*\(\s*token\s*=',
            "Bot(token=…) — bot token initialization"),
        (r'\bCommandHandler\s*\(',
            "CommandHandler — bot command wired"),
        (r'\bMessageHandler\s*\(',
            "MessageHandler — bot message handler"),
        (r'\bhosting_bot\b|\bhost_bot\b|\bpanel_bot\b',
            "Nested hosting service — recursive bot hosting"),
    ],

    # ── True backdoors ───────────────────────────────────────────
    "🔴 Backdoor": [
        (r'os\.system\s*\(\s*[^\)]{3,}\)',
            "os.system() — system command execution"),
        (r'subprocess\s*\.\s*(?:Popen|call|run)\s*\([^\n]*shell\s*=\s*True[^\n]*(?:input|stdin)',
            "Shell injection — user input piped to shell"),
        (r'marshal\.loads\s*\(',
            "marshal.loads() — obfuscated bytecode execution"),
        (r'ADMINNAME\s*=\s*["\'][^"\']{1,50}["\']',
            "Hardcoded secret admin trigger word"),
        (r'#.*LEGITIMATE LAGTA HAI|#.*dikhta aisa hai',
            "Deceptive comment — attacker ne add kiya"),
    ],

    # ── Suspicious network ───────────────────────────────────────
    "🟡 Suspicious Network": [
        (r'devil-api\.com|elementfx\.io',
            "Known malicious API endpoint"),
        (r'open\s*\(\s*["\'][/\\](?:root|etc|proc|sys)[^\)]*\)[^\n]*(?:requests|urllib)',
            "System file padh ke HTTP POST — data exfiltration"),
        (r'pastebin\.com/raw',
            "Pastebin se raw code download — remote code execution"),
        (r'bit\.ly/|tinyurl\.com/',
            "Shortened URL — hidden destination"),
        (r'\bngrok\b|\blocaltunnel\b|\bserveo\.net\b',
            "Tunnel library — server expose kar raha hai"),
        (r'requests\.post\s*\([^\n]*token[^\n]*\)',
            "Token bahar bhej raha hai via POST"),
    ],

    # ── Obfuscation ──────────────────────────────────────────────
    "🟡 Obfuscation": [
        (r'base64\.b64decode\s*\([^\n]+\)[^\n]*\bexec\b',
            "Base64 decode + exec — hidden code"),
        (r'zlib\.decompress\s*\([^\n]+\)[^\n]*\bexec\b',
            "Compressed code + exec — hidden code"),
        (r'(?:\\x[0-9a-fA-F]{2}){6,}',
            "Long hex string — obfuscated code"),
        (r'chr\s*\(\s*\d+\s*\)\s*\+\s*chr\s*\(\s*\d+\s*\)',
            "chr() chain — character encoding obfuscation"),
    ],

    # ── Resource abuse ───────────────────────────────────────────
    "🟠 Resource Abuse": [
        (r'multiprocessing\.Pool\s*\(\s*(?:None|\d{3,})',
            "Massive process pool — resource abuse"),
        (r'fork\s*\(\s*\)\s*[;\n].*fork\s*\(\s*\)',
            "Fork bomb pattern"),
        (r'while\s+True\s*:[^\n]*threading\.Thread',
            "Infinite loop + threading — CPU/memory abuse"),
    ],
}


WEIGHTS: Dict[str, int] = {
    "🔴 Data Theft":          40,
    "🔴 Backdoor":            35,
    "🔴 Exposed Credentials": 10,
    "🟠 Hidden Bot":           5,
    "🟠 Resource Abuse":      15,
    "🟡 Suspicious Network":  12,
    "🟡 Obfuscation":         12,
}

BOT_TOKEN_RE = re.compile(r'\b\d{8,10}:AA[A-Za-z0-9_-]{33}\b')
IP_RE        = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')


def static_scan(code: str) -> Dict[str, List[str]]:
    results: Dict[str, List[str]] = {}
    for category, pattern_list in PATTERNS.items():
        hits: List[str] = []
        for pattern, description in pattern_list:
            if re.search(pattern, code, re.IGNORECASE | re.MULTILINE):
                hits.append(description)
        if hits:
            results[category] = hits

    tokens = BOT_TOKEN_RE.findall(code)
    if tokens:
        results.setdefault("🔴 Exposed Credentials", [])
        results["🔴 Exposed Credentials"].append(
            f"Hardcoded Bot Token: {tokens[0][:15]}…  "
            f"({len(tokens)} token{'s' if len(tokens)>1 else ''} found)"
        )
    return results


def ast_scan(code: str) -> List[str]:
    findings: List[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        findings.append(
            f"Code parse nahi hua: {e} — encoded / obfuscated ho sakta hai"
        )
        return findings

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if (func.attr == 'walk'
                        and isinstance(func.value, ast.Name)
                        and func.value.id == 'os'
                        and node.args):
                    arg = node.args[0]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        if arg.value in ['/', '/root', '/etc', '/home', '/proc', '/var']:
                            findings.append(
                                f"os.walk('{arg.value}') — sensitive directory scan"
                            )

            if isinstance(func, ast.Name):
                fid = func.id
                if fid in ('eval', 'exec') and node.args:
                    arg0 = node.args[0]
                    if isinstance(arg0, (ast.Call, ast.Attribute)):
                        findings.append(
                            f"Dangerous: {fid}() — dynamic / remote code execution"
                        )

                if fid == '__import__' and node.args:
                    if isinstance(node.args[0], ast.Constant):
                        if node.args[0].value == 'os':
                            findings.append(
                                "Dynamic __import__('os') — code injection"
                            )

        if isinstance(node, ast.ClassDef):
            bad = {'harvest', 'steal', 'exfil', 'harvester', 'collector', 'grabber'}
            if any(b in node.name.lower() for b in bad):
                findings.append(f"Suspicious class name: {node.name}")

        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            val = node.value
            if val in ['/root', '/etc', '/proc', '/sys', '/home']:
                findings.append(f"Hardcoded sensitive path: '{val}'")

    return findings


def calculate_risk(static_findings: Dict[str, List[str]],
                   ast_findings: List[str]) -> int:
    score = 0
    for category, hits in static_findings.items():
        weight = WEIGHTS.get(category, 5)
        score += weight * min(len(hits), 3)

    unique_ast = list(dict.fromkeys(ast_findings))
    score += min(len(unique_ast) * 5, 20)

    return min(score, 100)


def get_verdict(risk_score: int,
                static_findings: Dict[str, List[str]]) -> Tuple[str, str]:
    has_blocking = any(
        static_findings.get(c)
        for c in ("🔴 Data Theft", "🔴 Backdoor")
    )
    cred_only = (
        "🔴 Exposed Credentials" in static_findings
        and not has_blocking
    )

    if risk_score >= 70 and has_blocking:
        return "DANGEROUS", "REJECT"
    if risk_score >= 40 and has_blocking:
        return "DANGEROUS", "REJECT"
    if cred_only and risk_score < 15:
        return "SUSPICIOUS", "APPROVE"
    if risk_score >= 30 or has_blocking:
        return "SUSPICIOUS", "MANUAL_REVIEW"
    return "SAFE", "APPROVE"


def _scan_archive(file_path: str) -> Dict[str, Any]:
    tmp = tempfile.mkdtemp()
    try:
        if file_path.endswith('.zip'):
            with zipfile.ZipFile(file_path, 'r') as z:
                for name in z.namelist():
                    if name.startswith('/') or '..' in name:
                        return {
                            "verdict": "DANGEROUS",
                            "risk_score": 99,
                            "findings": {
                                "🔴 Zip Slip Attack": [
                                    f"Dangerous path in ZIP: '{name}' — "
                                    "server files overwrite ho sakte hain!"
                                ]
                            },
                            "ast_findings": [],
                            "all_threats": ["🔴 Zip Slip Attack"],
                            "recommendation": "REJECT",
                            "summary": "ZIP Slip attack detected!",
                            "filename": os.path.basename(file_path),
                        }
                z.extractall(tmp)
        elif file_path.lower().endswith(('.tar.gz', '.tgz', '.tar')):
            with tarfile.open(file_path, 'r:*') as t:
                t.extractall(tmp)
        else:
            return {
                "verdict": "SUSPICIOUS", "risk_score": 20,
                "findings": {"🟡 Warning": ["Unknown archive format"]},
                "ast_findings": [], "all_threats": [],
                "recommendation": "MANUAL_REVIEW",
                "summary": "Unknown archive — manual check karo.",
                "filename": os.path.basename(file_path),
            }

        py_files = list(Path(tmp).rglob("*.py"))
        if not py_files:
            return {
                "verdict": "SUSPICIOUS", "risk_score": 20,
                "findings": {"🟡 Warning": ["Koi .py file nahi mili archive mein"]},
                "ast_findings": [], "all_threats": [],
                "recommendation": "MANUAL_REVIEW",
                "summary": "Archive mein Python files nahi hain.",
                "filename": os.path.basename(file_path),
            }

        worst: Optional[Dict[str, Any]] = None
        for py_file in py_files[:10]:
            try:
                code = py_file.read_text(errors='ignore')
                result = scan_code(code, py_file.name)
                if worst is None or result['risk_score'] > worst['risk_score']:
                    worst = result
            except Exception:
                continue

        return worst or {
            "verdict": "SAFE", "risk_score": 0,
            "recommendation": "APPROVE",
            "summary": "Safe lagti hai.", "all_threats": [],
            "findings": {}, "ast_findings": [],
            "filename": os.path.basename(file_path),
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def scan_code(code: str, filename: str = "file.py") -> Dict[str, Any]:
    sf = static_scan(code)
    af = ast_scan(code)
    risk = calculate_risk(sf, af)
    verdict, recommendation = get_verdict(risk, sf)

    all_threats: List[str] = [f"{c}: {h}" for c, hits in sf.items() for h in hits]
    all_threats += af

    if verdict == "DANGEROUS":
        summary = f"⚠️ File DANGEROUS hai! {len(all_threats)} threat(s) mili hain."
    elif verdict == "SUSPICIOUS":
        summary = "🔍 File suspicious hai. Admin se manual review karwao."
    else:
        summary = "✅ File safe lagti hai. Koi major threat nahi mila."

    return {
        "verdict":        verdict,
        "risk_score":     risk,
        "findings":       sf,
        "ast_findings":   af,
        "all_threats":    all_threats,
        "recommendation": recommendation,
        "summary":        summary,
        "filename":       filename,
    }


def scan_file(file_path: str) -> Dict[str, Any]:
    filename = os.path.basename(file_path)
    ext = filename.lower()

    try:
        if ext.endswith(('.zip', '.tar.gz', '.tgz', '.tar')):
            return _scan_archive(file_path)
        elif ext.endswith(('.py', '.pyc', '.pyo', '.js', '.ts')):
            with open(file_path, 'r', errors='ignore') as fh:
                code = fh.read()
            return scan_code(code, filename)
        else:
            return {
                "verdict":        "SUSPICIOUS",
                "risk_score":     30,
                "findings":       {"🟡 Warning": [f"Unknown file type: {ext}"]},
                "ast_findings":   [],
                "all_threats":    [f"Unknown file type: {ext}"],
                "recommendation": "MANUAL_REVIEW",
                "summary":        f"File type '{ext}' allow nahi hai.",
                "filename":       filename,
            }
    except Exception as e:
        return {
            "verdict":        "ERROR",
            "risk_score":     50,
            "findings":       {},
            "ast_findings":   [],
            "all_threats":    [f"Scan error: {e}"],
            "recommendation": "MANUAL_REVIEW",
            "summary":        f"Scan error: {e}",
            "filename":       filename,
        }


# টোকেনটি নিরাপদ রাখার জন্য এনভায়রনমেন্ট ভেরিয়েবল বা ফলব্যাক হিসেবে সেট করা হলো
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8923808337:AAGAaq0XkfLJ53YTJd17tIhZz_eNBD_qhZk")
