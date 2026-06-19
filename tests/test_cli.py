from agent_flight_recorder.cli import main


def test_help_prints_command_list(capsys):
    exit_code = main([])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Local flight recorder" in captured.out
    assert "start" in captured.out
    assert "commit-msg" in captured.out


def test_planned_command_exits_with_clear_message(capsys):
    try:
        main(["start"])
    except SystemExit as error:
        assert error.code == 2

    captured = capsys.readouterr()

    assert "planned but not implemented yet" in captured.err
