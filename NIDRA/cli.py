import argparse
import sys
from pathlib import Path
import NIDRA


def run_cli():
    """
    Run the scorer from the command line.
    """
    parser = argparse.ArgumentParser(description="NIDRA")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Scorer command
    score_parser = subparsers.add_parser("score", help="Run the scorer on a file or directory.")
    score_parser.add_argument("--input_path", required=True, help="Path to the input file (EDF) or directory.")
    score_parser.add_argument("--output_dir", required=True, help="Path to the output directory.")
    score_parser.add_argument("--scorer_type", required=True, choices=['psg', 'forehead'], help="Type of scorer.")
    score_parser.add_argument("--model_name", help="ez6 or ez6moe for Zmax. u-sleep-nsrr-2024 or u-sleep-nsrr-2024_eeg for PSG.", default='u-sleep-nsrr-2024_eeg')
    score_parser.add_argument("--no_plot", action="store_true", help="Do not generate a plot.")

    # If no command is given, show help. This is for when `nid` is called alone.
    if len(sys.argv) <= 1:
        parser.print_help(sys.stderr)
        sys.exit(1)
        
    args = parser.parse_args()

    if args.command == "score":
        input_path = Path(args.input_path)
        output_dir = Path(args.output_dir)

        files_to_process = []
        if input_path.is_dir():
            print(f"Scanning directory for EDF files: {input_path}")
            files_to_process.extend(sorted(input_path.glob('*.edf')))
            if not files_to_process:
                print("No EDF files found in the specified directory.")
                return
        elif input_path.is_file():
            if input_path.suffix.lower() == '.edf':
                files_to_process.append(input_path)
            else:
                print(f"Error: Input file {input_path} is not an EDF file.", file=sys.stderr)
                sys.exit(1)
        else:
            print(f"Error: Input path {input_path} is not a valid file or directory.", file=sys.stderr)
            sys.exit(1)

        model_name = args.model_name
        if model_name is None:
            if args.scorer_type == 'psg':
                model_name = 'u-sleep-nsrr-2024'
            elif args.scorer_type == 'forehead':
                model_name = 'ez6'

        for file in files_to_process:
            print(f"Processing: {file}")
            try:
                scorer = NIDRA.scorer(
                    scorer_type=args.scorer_type,
                    input_file=str(file),
                    output_dir=str(output_dir),
                    model_name=model_name,
                    epoch_sec=30
                )
                scorer.score(plot=not args.no_plot)
                print(f"Scoring for {file} complete. Results are in {output_dir}")
            except Exception as e:
                print(f"Error processing {file}: {e}", file=sys.stderr)
        
        if files_to_process:
            print("Batch processing finished.")