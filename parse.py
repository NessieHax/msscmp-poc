from argparse import ArgumentParser
import msscmp

def main():
    argparser = ArgumentParser()
    argparser.add_argument("filepath", action="store", help="Sound Bank filepath.")
    argparser.add_argument("-v", "--verbose", action="store_true", default=False, help="Output debug info (be verbose).")
    argparser.add_argument("-d", "--dump", action="store", default=None, metavar="path", help="Dumps bank sources into a directory.")
    args = argparser.parse_args()

    print(args)
    
    if not args.filepath.endswith(".msscmp"):
        raise Exception("Not a Soundbank(.msscmp) file")

    with open(args.filepath, "rb") as file: 
        msscmpfile = msscmp.MsscmpParser(args.verbose)
        msscmpfile.process(file)
        if args.dump is not None:
            print("Dumping...")
            msscmpfile.dumpAllSources(args.dump)

if __name__ == "__main__":
    main()