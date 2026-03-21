def cmd_next(project_dir: Path, extra_context: str = "") -> int:
    """Output the prompt for the next stage."""
    config = get_project_config(project_dir)
    mode = config.get("mode", "standard")
    mode_cfg = get_mode_config(mode)
    stages = mode_cfg["stages"]

    # Find next stage
    last = -1
    for s in reversed(stages):
        if is_stage_complete(project_dir, s):
            last = s
            break

    if last == stages[-1]:
        print("ALL_STAGES_COMPLETE")
        print("All stages are already complete. Nothing to do.")
        return 0

    try:
        next_stage = stages[stages.index(last) + 1] if last >= 0 else stages[0]
    except (ValueError, IndexError):
        next_stage = stages[0]

    # Check prerequisites (within this mode)
    current_idx = stages.index(next_stage)
    for prev_stage in stages[:current_idx]:
        if not is_stage_complete(project_dir, prev_stage):
            print(f"BLOCKED: Cannot proceed to Stage {next_stage}")
            print(f"  - Stage {prev_stage} ({ALL_STAGES[prev_stage]['name']}) not completed")
            return 1

    # Build and output prompt
    try:
        prompt = build_prompt(next_stage, project_dir, mode, extra_context)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return 1

    # Save prompt to file
    prompt_file = project_dir / ".veriflow" / f"stage_{next_stage}_prompt.md"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(prompt, encoding="utf-8")

    # Output
    print(f"STAGE:{next_stage}")
    print(f"NAME:{ALL_STAGES[next_stage]['name']}")
    print(f"MODE:{mode}")
    print(f"PROMPT_FILE:{prompt_file}")
    print("---BEGIN_PROMPT---")
    print(prompt)
    print("---END_PROMPT---")

    return 0

def cmd_validate(project_dir: Path, stage_id: int) -> int:
    """Run deterministic validation checks on a stage's outputs."""
    if stage_id < 0 or stage_id > 6:
        print(f"ERROR: Invalid stage {stage_id}. Valid range: 0-6")
        return 1

    config = get_project_config(project_dir)
    mode = config.get("mode", "standard")

    print(f"Validating Stage {stage_id}: {ALL_STAGES[stage_id]['name']}...")
    print(f"Mode: {mode}")
    print()

    passed, errors = validate_stage(stage_id, project_dir, mode)

    if passed:
        print(f"VALIDATION_PASSED")
        print(f"Stage {stage_id} outputs are valid.")
        print(f"Next: python veriflow_ctl.py complete -d \"{project_dir}\" {stage_id}")
    else:
        print(f"VALIDATION_FAILED")
        print(f"Stage {stage_id} has {len(errors)} error(s):")
        for err in errors:
            print(f"  [ERROR] {err}")

    return 0 if passed else 1

def cmd_complete(project_dir: Path, stage_id: int, summary: str = "") -> int:
    """Mark a stage as complete."""
    if stage_id < 0 or stage_id > 6:
        print(f"ERROR: Invalid stage {stage_id}. Valid range: 0-6")
        return 1

    if is_stage_complete(project_dir, stage_id):
        print(f"Stage {stage_id} is already marked complete.")
        return 0

    config = get_project_config(project_dir)
    mode = config.get("mode", "standard")

    # Validate before marking complete
    passed, errors = validate_stage(stage_id, project_dir, mode)
    if not passed:
        print(f"REFUSED: Stage {stage_id} validation failed. Cannot mark complete.")
        for err in errors:
            print(f"  [ERROR] {err}")
        return 1

    # Mark complete
    if not summary:
        summary = f"Stage {stage_id} completed at {datetime.now().isoformat()}"
    mark_stage_complete(project_dir, stage_id, summary)

    print(f"STAGE_COMPLETE:{stage_id}")
    print(f"Stage {stage_id} ({ALL_STAGES[stage_id]['name']}) marked COMPLETE.")

    # Show next step
    mode_cfg = get_mode_config(mode)
    stages = mode_cfg["stages"]

    if stage_id in stages:
        idx = stages.index(stage_id)
        if idx + 1 < len(stages):
            next_stage = stages[idx + 1]
            print(f"\nNext: python veriflow_ctl.py next -d \"{project_dir}\"")
        else:
            print("\nAll stages complete! Pipeline finished.")
    else:
        print(f"\nNext: python veriflow_ctl.py next -d \"{project_dir}\"")

    return 0

def cmd_rollback(project_dir: Path, target_stage: int) -> int:
    """Roll back to a target stage."""
    if target_stage < 0 or target_stage > 6:
        print(f"ERROR: Invalid target stage {target_stage}. Valid range: 0-6")
        return 1

    config = get_project_config(project_dir)
    mode = config.get("mode", "standard")
    mode_cfg = get_mode_config(mode)
    stages = mode_cfg["stages"]

    if target_stage not in stages:
        print(f"ERROR: Stage {target_stage} is not in mode '{mode}' (stages: {stages})")
        return 1

    # Find last completed stage
    last = -1
    for s in reversed(stages):
        if is_stage_complete(project_dir, s):
            last = s
            break

    if target_stage >= last:
        print(f"ERROR: Cannot rollback to Stage {target_stage} — last completed is Stage {last}")
        return 1

    # Clear markers from stages after target
    cleared = []
    for s in stages:
        if s > target_stage and is_stage_complete(project_dir, s):
            unmark_stage(project_dir, s)
            cleared.append(s)

    if cleared:
        print(f"ROLLBACK_DONE")
        print(f"Cleared completion markers for stages: {cleared}")
        print(f"Pipeline will resume from Stage {target_stage + 1}")
        print(f"\nNext: python veriflow_ctl.py next -d \"{project_dir}\"")
    else:
        print(f"No stages to clear after Stage {target_stage}")

    return 0

def cmd_mode(project_dir: Path, new_mode: Optional[str] = None) -> int:
    """Get or set execution mode."""
    config = get_project_config(project_dir)

    if new_mode is None:
        # Just display current mode
        current_mode = config.get("mode", "standard")
        mode_cfg = get_mode_config(current_mode)

        print(f"Current mode: {current_mode}")
        print(f"  {mode_cfg['display_name']}")
        print(f"  {mode_cfg['description']}")
        print(f"  Stages: {mode_cfg['stages']}")
        print()
        print("Available modes:")
        for m in ["quick", "standard", "enterprise"]:
            marker = "*" if m == current_mode else " "
            print(f"  [{marker}] {m}")
        print()
        print(f"To change mode: python veriflow_ctl.py mode -d \"{project_dir}\" <mode>")
        return 0

    # Set new mode
    if new_mode not in MODE_CONFIG:
        print(f"ERROR: Invalid mode '{new_mode}'")
        print(f"Valid modes: {list(MODE_CONFIG.keys())}")
        return 1

    # Check if any stages would be invalidated
    current_mode = config.get("mode", "standard")
    old_stages = set(get_mode_config(current_mode)["stages"])
    new_stages = set(get_mode_config(new_mode)["stages"])

    # Find stages that are completed but not in new mode
    extra_stages = old_stages - new_stages
    lost_stages = []
    for s in extra_stages:
        if is_stage_complete(project_dir, s):
            lost_stages.append(s)

    if lost_stages:
        print(f"WARNING: Changing to '{new_mode}' mode will lose completion status for stages: {lost_stages}")
        print("You may need to re-run these stages.")
        print()

    # Update config
    config["mode"] = new_mode
    save_project_config(project_dir, config)

    print(f"Mode changed from '{current_mode}' to '{new_mode}'")
    print()
    print(f"New configuration:")
    mode_cfg = get_mode_config(new_mode)
    print(f"  Stages: {mode_cfg['stages']}")
    print(f"  Validation: {mode_cfg['validation_level']}")
    print(f"  Features: {list(k for k, v in mode_cfg['features'].items() if v)}")
    print()
    print(f"Next: python veriflow_ctl.py next -d \"{project_dir}\"")

    return 0

def cmd_info(project_dir: Path, stage_id: int) -> int:
    """Show details about a specific stage."""
    if stage_id < 0 or stage_id > 6:
        print(f"ERROR: Invalid stage {stage_id}. Valid range: 0-6")
        return 1

    config = get_project_config(project_dir)
    mode = config.get("mode", "standard")
    mode_cfg = get_mode_config(mode)

    stage = ALL_STAGES[stage_id]
    done = is_stage_complete(project_dir, stage_id)
    in_mode = stage_id in mode_cfg["stages"]

    print(f"Stage {stage_id}: {stage['name']}")
    print(f"  Status: {'COMPLETE' if done else 'PENDING'}")
    print(f"  In current mode ({mode}): {'Yes' if in_mode else 'No'}")
    print(f"  Prompt file: {PROMPTS_DIR / stage['prompt']}")

    if in_mode:
        passed, errors = validate_stage(stage_id, project_dir, mode)
        print(f"  Validation: {'PASS' if passed else 'FAIL'}")
        if errors:
            for err in errors[:5]:
                print(f"    - {err}")

    return 0

# ── Main Entry Point ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="VeriFlow Controller v8.2 — Multi-Mode Design Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Initialize a new project
  python veriflow_ctl.py init -d ./my_project

  # Check status
  python veriflow_ctl.py status -d ./my_project

  # Change mode
  python veriflow_ctl.py mode -d ./my_project quick

  # Execute pipeline
  python veriflow_ctl.py next -d ./my_project
  python veriflow_ctl.py validate -d ./my_project 3
  python veriflow_ctl.py complete -d ./my_project 3

  # Rollback
  python veriflow_ctl.py rollback -d ./my_project 1
""")

    parser.add_argument("command",
                       choices=["init", "status", "next", "validate", "complete",
                               "rollback", "info", "mode"],
                       help="Subcommand to run")
    parser.add_argument("arg", nargs="?", default=None,
                       help="Stage number for validate/complete/rollback/info, or mode for mode command")
    parser.add_argument("-d", "--project-dir", type=Path, default=Path("."),
                       help="Project root directory (default: current directory)")
    parser.add_argument("--summary", type=str, default="",
                       help="Summary text for complete command")
    parser.add_argument("--extra-context", type=str, default="",
                       help="Extra context to inject into the prompt")

    args = parser.parse_args()
    project_dir = args.project_dir.resolve()

    # Dispatch
    if args.command == "init":
        return cmd_init(project_dir)

    elif args.command == "status":
        return cmd_status(project_dir)

    elif args.command == "mode":
        new_mode = args.arg
        return cmd_mode(project_dir, new_mode)

    elif args.command == "next":
        return cmd_next(project_dir, extra_context=args.extra_context)

    elif args.command == "validate":
        if args.arg is None or not args.arg.isdigit():
            print("ERROR: validate requires a stage number")
            return 1
        return cmd_validate(project_dir, int(args.arg))

    elif args.command == "complete":
        if args.arg is None or not args.arg.isdigit():
            print("ERROR: complete requires a stage number")
            return 1
        return cmd_complete(project_dir, int(args.arg), summary=args.summary)

    elif args.command == "rollback":
        if args.arg is None or not args.arg.isdigit():
            print("ERROR: rollback requires a target stage")
            return 1
        return cmd_rollback(project_dir, int(args.arg))

    elif args.command == "info":
        if args.arg is None or not args.arg.isdigit():
            print("ERROR: info requires a stage number")
            return 1
        return cmd_info(project_dir, int(args.arg))

    return 0

if __name__ == "__main__":
    sys.exit(main())
