#!/usr/bin/env bash
# Prepare the hand-written LangGraph test course for testing the lesson pipeline.
# Usage: tests/fixtures/make-test-course.sh <target-dir>
# Then, in Claude Code started with the plugin: /codelabgen:lesson all --course <target-dir>
set -euo pipefail

target=${1:?usage: $0 <target-dir>}
here=$(cd "$(dirname "$0")" && pwd)

codelabgen init "$target" --topic LangGraph --lang ru --version 1.2.15
cp "$here/langgraph-curriculum.yaml" "$target/.codelabgen/curriculum.yaml"
export CODELABGEN_COURSE=$target

codelabgen curriculum validate
# The curriculum is hand-written: skip the research and curriculum phases.
for phase in recon sources gate_sources; do codelabgen state phase "$phase"; done
codelabgen state phase topics --approved
for phase in curriculum gate_plan; do codelabgen state phase "$phase"; done
codelabgen state phase scaffold --approved
codelabgen scaffold course
codelabgen state phase lessons
codelabgen state show
