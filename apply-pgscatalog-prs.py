import argparse
import time
import os
import shutil
import subprocess
import pandas as pd
import yaml

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

parser = argparse.ArgumentParser()
parser.add_argument("-g", "--genetic", default=None, type=str,
                    help="Absolute path prefix to plink trio bed/bim/fam files "
                         "(for example, for the file '/emc/data/File.bed' this would be '/emc/data/File')")
parser.add_argument("-p", "--prs-wm", default=None, type=str,
                    help="Absolute path to PRS weight matrix downloaded from PGSCatalog")
# parser.add_argument("--rsid-col", default=None, type=str,
#                     help="Column name, where rsID is stored in PRS weight matrix")
# parser.add_argument("--chrom-col", default=None, type=str,
#                     help="Column name, where chromosome is stored in PRS weight matrix")
# parser.add_argument("--pos-col", default=None, type=str,
#                     help="Column name, where position within chromosome is stored in PRS weight matrix")
# parser.add_argument("--effect-allele-col", default=None, type=str,
#                     help="Column name, where effect allele is stored in PRS weight matrix")
# parser.add_argument("--ref-allele-col", default=None, type=str,
#                     help="Column name, where reference allele is stored in PRS weight matrix")
# parser.add_argument("--beta-col", default=None, type=str,
#                     help="Column name, where effect size (beta, log(OR)) is stored in PRS weight matrix")
parser.add_argument("-o", "--out", default=None, type=str,
                    help="Output path prefix "
                         "(for example, to generate the files '/home/abc123/prs/output.profile' "
                         "this would be '/home/abc123/prs/output')")
arguments = parser.parse_args()

console = Console()
layout = Layout()
live = Live(console=console)


def check_input(args):
    if args.genetic is None:
        print("plink genetic data are required")
        parser.print_help()
        exit(1)
    for ext in ("bed", "bim", "fam"):
        if not os.path.isfile(f"{args.genetic}.{ext}"):
            print(f"plink genetic data are malformed - {args.genetic}.{ext} is missing")
            exit(4)
    if args.prs_wm is None:
        print("PRS weight matrix is required")
        parser.print_help()
        exit(2)
    if not os.path.isfile(args.prs_wm):
        print(f"PRS weight matrix file does not exist")
        exit(5)
    if args.out is None:
        print("Output prefix is required")
        parser.print_help()
        exit(3)
    # if (args.rsid_col is None) and ((args.chrom_col is None) or (args.pos_col is None)):
    #     print("Either rsID column or chromosome and position columns should be provided")
    #     parser.print_help()
    #     exit(6)
    # if args.effect_allele_col is None:
    #     print("Effect allele column should be provided")
    #     parser.print_help()
    #     exit(6)
    # if args.beta_col is None:
    #     print("Effect size (beta, log(OR)) column should be provided")
    #     parser.print_help()
    #     exit(6)


def print_error_misaligned_files():
    print("ERROR: Less that a half of the PGSCatalog SNPs are available.")
    print("ERROR: This may be for one of the following reasons:")
    print("ERROR: 1. Either you are using un-imputed plink data. THEN you have to impute the data.")
    print("ERROR: *2. Or you have data imputed to a very specific panel that does not contain a lot of common variants "
          "(happens seldom, probably won't happen to you). THEN you have to impute the data to a more general panel.")
    print("ERROR: 3. Or the PRS weight matrix is using a different reference genome than your plink data. "
          "THEN you need to liftover your data to the correct reference genome.")
    print("ERROR: *4. Or the PRS was done using a very specific chip and contains such unique SNPs "
          "that no imputation panel has them (happens seldom, probably won't happen to you). "
          "THEN you have to find an imputation panel that has these SNPs and impute the data to this panel.")
    print("Here is your troubleshoot guide:")
    print("---")
    print("Q: How do I figure out if the data are imputed or not, and to which panel? (problems 1,2)")
    print("A: Ask your data provider (typically the phenomics platform) about it. "
          "Imputed data will contain at least a few millions SNPs.")
    print("---")
    print("Q: How do I figure out if the reference genomes are different between the data? (problem 3)")
    print("A: Ask your data provider (typically the phenomics platform) which reference genome was used for your data. "
          "Check the reference genome of your score in the 'PGS Catalog Metadata' Excel sheet "
          "at the http://www.pgscatalog.org/downloads/ . See, if they match or not.")
    print("---")
    print("Q: I have no idea about reference genomes and imputation, what do I do?")
    print("A: We did our best we could do automatically processing the PGSCatalog data. "
          "But if want to run the analysis, it is ultimately your responsibility to assure that you have proper data. "
          "You don't want to publish the results that are fake because you mishandled the data, do you? ")
    print("Ideally, your data provider (typically the phenomics platform) would *always* supply data to you "
          "in the same reference genome, imputed to the same imputation panel. If this was the case, this script would "
          "have been smarter at handling these issues automatically. But at the moment when this script was written "
          "this was not the case =/ Unfortunately, this means it is your problem now to figure it all out "
          "or to force your data provider to work properly ¯\_(ツ)_/¯")
    print("---")
    print("Q: I still have no idea, but I need this PRS, what do I do?")
    print("A: Invite a bioinformatician with programming / data science background, explain your problem to them, "
          "and show this error message.")


def print_non_annotated_plink_file_error():
    printout("ERROR: Your plink data have no variants IDs at all.")
    printout("ERROR: Ask your data supplier (probably the phenomics platform) to annotate it using dbSNP,")
    printout("ERROR: or at least assign the dummy 'chrom:pos' ids to the SNPs, if you know what you are doing.")
    printout("ERROR: This script do *not* need *dbSNP* variant IDs, but it *does* need *some* IDs.")
    printout("---")
    printout("P.S. We do *not* recommend using any kind of non-dbSNP ids,")
    printout(" because your colleagues' scripts may, unfortunately, rely on dbSNP annotation.")
    printout(" If you are ok with having 'chrom:pos' encoding and you think that you know what you are doing,")
    printout(" then you must be able to construct the annotation command using bash 'cut' and 'paste' yourself.")


# def input_files_qc(pgscatalog_df: pd.DataFrame, plink_variants_df: pd.DataFrame):
#     # Remove indels - we are unsure if they are dangerous, but we will remove them just in case
#     lines_were = pgscatalog_df.shape[0]
#     nucleotides = ("A", "C", "G", "T")
#     df = pgscatalog_df[pgscatalog_df["effect_allele"].isin(nucleotides)]
#     if "reference_allele" in df.columns:
#         df = df[df["reference_allele"].isin(nucleotides)]
#     printout(f"  {df.shape[0]} SNPs were preserved, {lines_were - df.shape[0]} indels were filtered")
#
#     # Check if plink files have any annotation at all
#     if (plink_variants_df["rsid"].nunique() == 1) and (plink_variants_df["rsid"].unique()[0] == "."):
#         print_non_annotated_plink_file_error()
#         exit(30)
#     # Chromosome names cutting - changes dataframes inplace
#     chrom_cutter = lambda x: x[3:] if x.startswith("chr") else x
#     pgscatalog_df["chr_name"] = pgscatalog_df["chr_name"].astype(str).apply(chrom_cutter)
#     plink_variants_df["chr_name"] = plink_variants_df["chr_name"].astype(str).apply(chrom_cutter)


GENERAL_DATA_FORMAT = """
pgscatalog_df: A dataframe of PGSCatalog score weight matrix data with columns:
            | chr_name | chr_position | effect_allele | reference_allele [may be omitted] | effect_weight |
            |----------|--------------|---------------|-----------------------------------|---------------|
            |     1    |   5894332    |       T       |                 G                 |   -0.000073   |
                    
plink_variants_df: A dataframe of local plink variants data with columns:
            | chr_name | rsid | chr_position | base_allele [A1] | alternative_allele [A2] |
            |----------|------|--------------|------------------|-------------------------|
            |     1    | rs12 |   5894332    |         T        |            G            |
"""


def prep_keys_rsid(pgscatalog_df: pd.DataFrame, plink_variants_df: pd.DataFrame):
    # QC the plink rsid
    if (plink_variants_df["rsid"].nunique() == 1) and (plink_variants_df["rsid"].unique()[0] == "."):
        print_non_annotated_plink_file_error()
        exit(30)
    # Figuring out the key
    rsid_column = Prompt.ask(
        "Which column in PRS file contains the [bold red]rsID[/bold red]?",
        choices=list(pgscatalog_df.columns),
    )
    # Creating keys
    pgscatalog_df["pos_key"] = pgscatalog_df[rsid_column].astype(str)
    console.print(layout)


def prep_keys_chrompos(pgscatalog_df: pd.DataFrame, plink_variants_df: pd.DataFrame):
    # Figuring out the key
    chrom_column = Prompt.ask(
        "Which column in PRS file contains the [bold red]chromosome[/bold red]?",
        choices=list(pgscatalog_df.columns),
    )
    pos_column = Prompt.ask(
        "Which column in PRS file contains the [bold red]position[/bold red]?",
        choices=list(pgscatalog_df.columns),
    )
    # Creating keys
    pgscatalog_df["pos_key"] = pgscatalog_df[chrom_column].astype(str) + ":" + pgscatalog_df[pos_column].astype(str)
    console.print(layout)


def check_the_files_match(pgscatalog_df, plink_variants_df):
    # Heuristics of mapping
    amount_of_shared_keys = len(set(plink_variants_df["rsid"]).intersection(pgscatalog_df["pos_key"]))
    amount_of_plink_variants = plink_variants_df.shape[0]
    amount_of_pgscatalog_variants = pgscatalog_df.shape[0]
    if amount_of_shared_keys > 0.50 * amount_of_pgscatalog_variants:
        printout(f"{amount_of_shared_keys} ({amount_of_shared_keys / amount_of_pgscatalog_variants:.0%}) "
                 f"variants from PGSCatalog are available in your plink data ({amount_of_plink_variants} variants)")
        return True
    return False


def maybe_unpack(prs_wm_text_file: str):
    if prs_wm_text_file.endswith(".txt.gz"):
        printout("gzipped PGSCatalog file found, unpacking...")
        process = subprocess.run([
            "gunzip", prs_wm_text_file
        ])
        assert process.returncode == 0, "  ERROR: gunzip crashed"
        prs_wm_text_file = prs_wm_text_file[:-3]
    return prs_wm_text_file


def load_prs_wm(prs_wm_text_file: str):
    # Load, remove # part of the header
    df: pd.DataFrame = pd.read_table(
        prs_wm_text_file,
        header=0,
        comment='#'  # to skip the PGSCatalog-specific header
    )

    printout(f"  {df.shape[0]} SNPs discovered in the PRS weight matrix")
    if df.shape[0] < 1000:
        printout("  WARNING: This looks like a more classical GRS! But we will continue anyways")

    return df


def annotate_pgscatalog_file(pgscatalog_df):
    # Annotate the essential beta and effect allele columns:
    beta_column = Prompt.ask(
        "Which column in PRS file contains the [bold red]beta[/bold red]?",
        choices=list(pgscatalog_df.columns),
    )
    console.print(layout)

    effect_allele_column = Prompt.ask(
        "Which column in PRS file contains the [bold red]effect allele[/bold red]?",
        choices=list(pgscatalog_df.columns),
    )
    console.print(layout)

    columns = {
        beta_column: "effect_weight",
        effect_allele_column: "effect_allele",
    }
    return columns


def render_file_table(df, title):
    df_visual_table = Table(*df.columns, title=title)
    for row in df.values[:5]:
        df_visual_table.add_row(*list(map(str, row)))
    return df_visual_table


def load_data(plink_prefix: str, prs_wm_text_file: str):
    # Unpack, if required
    prs_wm_text_file = maybe_unpack(prs_wm_text_file)

    # Variables
    processed_wm_text_file = prs_wm_text_file + ".annotated"

    # Load PGSCatalog data
    printout("Loading PGSCatalog data and removing comments and indels...")
    pgscatalog_df = load_prs_wm(prs_wm_text_file)
    layout["top"]["leftfile"].update(render_file_table(pgscatalog_df, title="PRS WM file"))
    console.print(layout)
    # Annotate PGSCatalog data
    columns = annotate_pgscatalog_file(pgscatalog_df)
    pgscatalog_df.rename(columns, inplace=True)
    layout["top"]["leftfile"].update(render_file_table(pgscatalog_df, title="PRS WM file"))
    console.print(layout)

    # Load plink data
    printout("Loading plink data...")
    plink_variants_df = pd.read_table(
        plink_prefix+".bim",
        sep="\t", header=None,
        # fixed structure of plink .bim files - https://www.cog-genomics.org/plink/1.9/formats#bim
        names=["chr_name", "rsid", "dummy_cm_position", "chr_position", "base_allele", "alternative_allele"],
        usecols=["chr_name", "rsid", "chr_position", "base_allele", "alternative_allele"],
    )
    layout["top"]["rightfile"].update(render_file_table(plink_variants_df, title="plink data"))
    console.print(layout)

    printout("All data are loaded\n-----------------")

    return pgscatalog_df, plink_variants_df, processed_wm_text_file


def preprocess_data(pgscatalog_df, plink_variants_df, processed_wm_text_file):
    # First, ask how to match
    RSID = "rsid"
    CHROMPOS = "pos"
    how_to_match = Prompt.ask(
        "Would you prefer matching plink data on existing identifiers (rsid) "
        "or create a novel key from chromosome:position pair (pos)?",
        choices=[RSID, CHROMPOS],
    )
    if how_to_match == RSID:
        printout("Trying to match PGSCatalog data with plink data using rsID...")
        prep_keys_rsid(pgscatalog_df, plink_variants_df)
    elif how_to_match == CHROMPOS:
        printout("Trying to match PGSCatalog data with plink data using chromosome and position...")
        prep_keys_chrompos(pgscatalog_df, plink_variants_df)
    else:
        raise RuntimeError("Unreacheble code")
    was_match_successful = check_the_files_match(pgscatalog_df, plink_variants_df)
    # QC
    # input_files_qc(pgscatalog_df, plink_variants_df)
    # Assess the results and create final matching that plink will be able to use
    pgscatalog_df[["pos_key", "effect_allele", "effect_weight"]].to_csv(processed_wm_text_file, sep="\t", float_format="%.4e")
    if not was_match_successful:
        print_error_misaligned_files()
        exit(40)


def plink_qc(df: pd.DataFrame):
    avg_snps_used = df["CNT2"].mean()
    bad_samples = df.index[df["CNT2"] < 0.95 * avg_snps_used]
    if not bad_samples.empty:
        printout("WARNING: The following samples has a lot of missing SNPs "
                 "(more than 5% of SNPs, available on average in other samples)")
        printout("They will dropped from the following analysis")
        printout(",".join(bad_samples))
        df.drop(bad_samples, inplace=True)
    return df


def calculate_prs(plink_prefix: str, processed_wm_text_file: str, output_prefix: str):
    # Variables
    plink_output_file = output_prefix + ".profile"
    prs_output_file = output_prefix + ".prs"

    # Running plink
    printout("Running plink PRS scoring...")
    process = subprocess.run([
        "plink", "--bfile", plink_prefix, "--score", processed_wm_text_file,
        "1",  # variant ID column index, 1-based
        "2",  # effect allele column index, 1-based
        "3",  # beta column index, 1-based
        "sum", "header",
        "--out", output_prefix,
    ], universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.returncode != 0 or not os.path.isfile(plink_output_file):
        print("ERROR: plink has failed")
        print(process.stderr)
        exit(20)

    # Parsing plink results
    printout("Parsing plink results...")
    df = pd.read_table(plink_output_file, sep="\s+", index_col="IID")
    df: pd.DataFrame = plink_qc(df)
    df[["SCORESUM"]].to_csv(prs_output_file, sep="\t", float_format="%.4e")
    # Done
    printout(f"PRS is saved to {prs_output_file}")


def parse_pgscatalog_wm_columns(args):
    columns = {
        args.effect_allele_col: "effect_allele",
        args.beta_col: "effect_weight",
    }
    if args.ref_allele_col is not None:
        columns[args.ref_allele_col] = "reference_allele"
    if args.rsid_col is not None:
        columns[args.rsid_col] = "rsID"
    if args.chrom_col is not None:
        columns[args.chrom_col] = "chr_name"
    if args.pos_col is not None:
        columns[args.pos_col] = "chr_position"
    return columns


def printout(text):
    # noinspection PyUnresolvedReferences
    old_text = layout["main"].renderable.renderable
    old_lines = old_text.split("\n")
    new_lines = text.split("\n")
    new_text = "\n".join((old_lines + new_lines)[-30:])
    layout["main"].update(Panel(new_text))
    console.print(layout)


def render():
    # Divide the "screen" in to three parts
    layout.split(
        Layout(name="header", size=3),
        Layout(name="top", size=12),
        Layout(name="main", ratio=1),
        # Layout(name="cmd", size=3),
    )
    # Divide the "side" layout in to two
    layout["top"].split(
        Layout(name="leftfile", ratio=1),
        Layout(name="rightfile", ratio=1),
        direction="horizontal",
    )

    layout["header"].update(Panel("PRS Tool"))
    layout["main"].update(Panel("Loading..."))
    layout["top"]["leftfile"].update(Panel("PRS WM file will appear here"))
    layout["top"]["rightfile"].update(Panel("Genetic data will appear here"))
    console.print(layout)


def main(args):
    check_input(args)
    plink_prefix, prs_wm_text_file, output_prefix = args.genetic, args.prs_wm, args.out
    render()
    pgscatalog_df, plink_variants_df, processed_wm_text_file = load_data(plink_prefix, prs_wm_text_file)
    # TODO: reuse
    # is_to_reuse = False
    # if os.path.isfile(processed_wm_text_file):
    #     is_to_reuse = Confirm.ask(
    #         "PGS files were preprocessed - would you like to re-use them (recommended) instead of processing again?",
    #     )
    preprocess_data(pgscatalog_df, plink_variants_df, processed_wm_text_file)
    calculate_prs(plink_prefix, processed_wm_text_file, output_prefix)


if __name__ == "__main__":
    main(arguments)