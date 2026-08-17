"""Local chat UI for testing Raiden's investigator + executor, with voice.

Run with:
    pip install -r requirements.txt -r requirements-frontend.txt
    streamlit run frontend/app.py

Voice input uses st.chat_input's built-in microphone recorder (no
sounddevice needed) and transcribes with local Whisper. Voice replies use
local Piper TTS, played back in-browser via st.audio — nothing shells out
to an OS-level audio player here.

This is a testing/demo surface only — it calls the exact same read-only
investigator and confirm-gated executor used by the CLI/voice-loop paths.
It never runs a runbook without an explicit "Confirm & run" click.
"""

import shlex
import sys
import tempfile
from pathlib import Path

import streamlit as st
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.executor.executor import RunbookExecutor, RunbookNotAllowedError
from src.investigator import investigate
from src.investigator.action_proposer import ActionProposalError, propose_action
from src.resolver.resolver import (
    AmbiguousProjectError,
    ProjectNotFoundError,
    load_catalog,
    resolve_project,
)
from src.voice.stt.transcribe import transcribe as stt_transcribe
from src.voice.tts.speak import synthesize as tts_synthesize

st.set_page_config(page_title="Raiden", page_icon="⚡", layout="wide")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_runbook" not in st.session_state:
    st.session_state.pending_runbook = None
if "pending_action" not in st.session_state:
    st.session_state.pending_action = None


def _load_runbook_def(runbook_id, runbooks_dir):
    path = Path(runbooks_dir) / f"{runbook_id}.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _transcribe_audio(uploaded_audio, whisper_model):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(uploaded_audio.getvalue())
        wav_path = tmp.name
    return stt_transcribe(wav_path, model_size=whisper_model)


with st.sidebar:
    st.title("⚡ Raiden")
    st.caption("Local-first DevOps investigator — chat test UI")

    catalog_dir = st.text_input("Catalog directory", value="catalog")
    model = st.text_input("Ollama model", value="llama3.1:8b")
    audit_log_path = st.text_input("Audit log path", value="audit/session.jsonl")
    evidence_db_path = st.text_input("Evidence DB path", value="audit/evidence.sqlite3")

    st.divider()
    st.subheader("Voice")
    whisper_model = st.selectbox("Whisper model (speech-to-text)", ["base", "small", "medium"], index=0)
    voice_replies = st.checkbox("Speak replies out loud (Piper TTS)")
    tts_model_path = st.text_input(
        "Piper voice model (.onnx)",
        value=".voice-models/en_US-lessac-medium.onnx",
        disabled=not voice_replies,
    )

    st.divider()
    st.subheader("Catalog entries")
    try:
        entries = load_catalog(catalog_dir)
    except FileNotFoundError:
        entries = []
        st.warning(f"No catalog directory at '{catalog_dir}'")

    for entry in entries:
        with st.expander(entry["id"]):
            st.write("**Aliases:**", ", ".join(entry.get("aliases", [])))
            for cloud in entry.get("clouds", []):
                services = ", ".join(s.get("service", s.get("type")) for s in cloud.get("services", []))
                st.write(f"- {cloud['provider']}: {services}")
            st.write("**Runbooks allowed:**", ", ".join(entry.get("runbooks_allowed", [])) or "(none)")

    st.divider()
    st.subheader("Propose a runbook")
    st.caption("Read-only chat above never runs a runbook. This panel does, but only after you explicitly confirm.")

    runbook_projects = [e for e in entries if e.get("runbooks_allowed")]
    if runbook_projects:
        project_ids = [e["id"] for e in runbook_projects]
        selected_project_id = st.selectbox("Project", project_ids)
        selected_entry = next(e for e in runbook_projects if e["id"] == selected_project_id)
        runbook_id = st.selectbox("Runbook", selected_entry["runbooks_allowed"])

        try:
            runbook_def = _load_runbook_def(runbook_id, "runbooks")
        except FileNotFoundError:
            runbook_def = None
            st.error(f"No runbooks/{runbook_id}.yaml found")

        if runbook_def:
            st.write(runbook_def.get("description", ""))
            params = {}
            for name, schema in runbook_def.get("params", {}).get("properties", {}).items():
                params[name] = st.text_input(f"param: {name}", key=f"param_{runbook_id}_{name}")

            if st.button("Propose command"):
                executor = RunbookExecutor(runbooks_dir="runbooks", audit_log_path=audit_log_path)
                try:
                    command, requires_confirmation = executor.propose(runbook_id, params, selected_entry)
                    st.session_state.pending_runbook = {
                        "command": command,
                        "requires_confirmation": requires_confirmation,
                        "runbook_id": runbook_id,
                    }
                except (RunbookNotAllowedError, ValueError) as e:
                    st.error(str(e))
                    st.session_state.pending_runbook = None
    else:
        st.caption("No catalog entries have any runbooks_allowed.")

    if st.session_state.pending_runbook:
        pending = st.session_state.pending_runbook
        st.code(" ".join(pending["command"]), language="bash")
        st.warning("This will actually execute the command above against real infrastructure.")
        if st.button("⚠️ Confirm & run", type="primary"):
            executor = RunbookExecutor(runbooks_dir="runbooks", audit_log_path=audit_log_path)
            result = executor.execute(pending["command"], confirmed=True)
            st.session_state.pending_runbook = None
            if result.returncode == 0:
                st.success(f"Exit 0\n\n{result.stdout}")
            else:
                st.error(f"Exit {result.returncode}\n\n{result.stderr}")
        if st.button("Cancel"):
            st.session_state.pending_runbook = None
            st.rerun()


mode = st.segmented_control(
    "Mode", ["Investigate an issue", "Take an action"], default="Investigate an issue"
)
act_mode = mode == "Take an action"

st.header("Act" if act_mode else "Investigate")
if act_mode:
    st.caption(
        "The model drafts an aws/gcloud/kubectl/gh command from your request. "
        "Nothing runs until you review (and can edit) it below and explicitly confirm."
    )

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("audio"):
            st.audio(msg["audio"], format="audio/wav")


def render_pending_action_card():
    """Renders the review/edit/confirm card for the current pending action,
    if any. Called once per run, after any new submission has already shown
    its own chat bubble (which includes the project + explanation) — this
    card only needs the editable command and the confirm/cancel controls."""
    if not st.session_state.pending_action:
        return
    pending = st.session_state.pending_action
    with st.chat_message("assistant"):
        st.markdown(f"Proposed command for `{pending['entry_id']}`:")
        edited = st.text_area(
            "Review and edit the command before running it (a local model can't look up "
            "real values like AMI/VPC ids — verify these yourself)",
            value=" ".join(pending["command"]),
            key="pending_action_edit",
        )
        confirm_col, cancel_col = st.columns(2)
        with confirm_col:
            if st.button("⚠️ Confirm & run", type="primary", key="confirm_action"):
                try:
                    edited_command = shlex.split(edited)
                    entry = next(e for e in entries if e["id"] == pending["entry_id"])
                    executor = RunbookExecutor(runbooks_dir="runbooks", audit_log_path=audit_log_path)
                    validated_command = executor.validate_free_form(edited_command, entry)
                    result = executor.execute(validated_command, confirmed=True)
                    if result.returncode == 0:
                        st.success(f"Exit 0\n\n{result.stdout}")
                    else:
                        st.error(f"Exit {result.returncode}\n\n{result.stderr}")
                except (RunbookNotAllowedError, ValueError) as e:
                    st.error(str(e))
                st.session_state.pending_action = None
        with cancel_col:
            if st.button("Cancel", key="cancel_action"):
                st.session_state.pending_action = None
                st.rerun()


submission = st.chat_input(
    "What do you want to do?" if act_mode else "What's broken?",
    accept_audio=True,
    audio_sample_rate=16000,
)

if submission:
    report = submission.text
    heard_audio_bytes = None

    if submission.audio is not None:
        heard_audio_bytes = submission.audio.getvalue()
        with st.spinner("Transcribing..."):
            report = _transcribe_audio(submission.audio, whisper_model)

    if not report:
        st.warning("No speech or text detected in that submission — try again.")
    else:
        user_entry = {"role": "user", "content": report}
        if heard_audio_bytes:
            user_entry["audio"] = heard_audio_bytes
        st.session_state.messages.append(user_entry)

        with st.chat_message("user"):
            st.markdown(report)
            if heard_audio_bytes:
                st.audio(heard_audio_bytes, format="audio/wav")

        with st.chat_message("assistant"):
            entry = None
            try:
                entry = resolve_project(report, catalog_dir)
            except (ProjectNotFoundError, AmbiguousProjectError) as e:
                reply = str(e)
                st.markdown(reply)

            if entry is None:
                pass
            elif act_mode:
                if not entry.get("free_form_actions_allowed", False):
                    reply = (
                        f"Free-form actions aren't enabled for `{entry['id']}` — "
                        "set `free_form_actions_allowed: true` in its catalog entry first."
                    )
                    st.markdown(reply)
                else:
                    with st.spinner(f"Drafting a command for {entry['id']} with {model}..."):
                        try:
                            command, explanation = propose_action(report, entry, model=model)
                        except ActionProposalError as e:
                            command, explanation = [], f"Couldn't draft a command: {e}"

                    if command:
                        st.session_state.pending_action = {
                            "entry_id": entry["id"],
                            "command": command,
                            "explanation": explanation,
                        }
                        reply = (
                            f"**Project:** `{entry['id']}`\n\n{explanation}\n\n"
                            "Review the proposed command below before confirming."
                        )
                    else:
                        reply = f"**Project:** `{entry['id']}`\n\n{explanation}"
                    st.markdown(reply)
            else:
                with st.spinner(f"Investigating {entry['id']} with {model}... (can take a while on CPU)"):
                    reply = investigate(
                        report,
                        entry,
                        audit_log_path=audit_log_path,
                        evidence_db_path=evidence_db_path,
                        model=model,
                    )
                st.markdown(f"**Project:** `{entry['id']}`\n\n{reply}")

            if voice_replies:
                try:
                    with st.spinner("Synthesizing speech..."):
                        reply_audio = tts_synthesize(reply, tts_model_path)
                    st.audio(reply_audio, format="audio/wav", autoplay=True)
                except (SystemExit, RuntimeError, FileNotFoundError) as e:
                    st.warning(f"Couldn't synthesize speech: {e}")

        st.session_state.messages.append({"role": "assistant", "content": reply})

render_pending_action_card()
