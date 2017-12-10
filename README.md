# ynabsplitter
A Python script that automatically splits transactions in YNAB4 budgets.

## WARNING
This script **modifies** your YNAB budget files! I've tested it on my own files and believe it will at least do no harm. However, you use this script at your own risk and should ensure you have backups of all YNAB files before use.

## Usage
You'll need to set up a config file first. There's an example named `ynabsplitter.json` in the repo. These are the keys in the config file:

### Configuration
#### windowsYnabDir
This is the path to your YNAB directory--the directory that contains all of your "Budget~12345678.ynab4" directories. If you're using YNAB's cloud sync, this is probably `c:/Users/<you>/Dropbox/YNAB`.
#### macYnabDir
Same as windowsYnabDir, but will be used on Macs.
#### toSplitCategoryPath
This is the category that you'll temporarily assign to transactions that you want to be split by the script. It should follow the form "Master Category/Category". For example, my value here is "Chaff/To Split".
#### budgetName
The name of the budget you want to modify. This should be the name of one of the directories in your windows/macYnabDir.
#### smallerSplitDenominator
This value defines how splits are made. To split transactions evenly, use `2`. To make the smaller split 1/3 of the total and the larger split 2/3, use `3`. Specifying the denominator is a bit awkward, but it works best for my personal use.
#### smallerSplitCategoryPath
This should have the same form as toSplitCategoryPath. It specifies which category to assign to the smaller split of each transaction that's modified. To leave these splits uncategorized, use `null` here.
#### largerSplitCategoryPath
Same as smallerSplitCategoryPath, but for the larger split.
#### ledgerOutputFormat
To disable this feature, use `null`. This value is useful for sending the splits to a spreadsheet. After writing the splits to the budget file, the script will copy to the clipboard one line for each modified transaction. You can specify the format of the lines here. If you had a spreadsheet for your shared expenses with someone else like this:

| Date Entered | Date of Transaction | Amount | Comment |
|---|---|---|---|
| 2017-12-10 | 2017-12-07 | 16.05 | J bought Safeway 32.10 |

You could use `{date}\t{txDate}\t{splitAmount}\tJ bought {payee} {totalAmount}` for this config value. After the script ran, you could paste into the spreadsheet (copying to clipboard is done automatically) and have all the split information there, too!

### Running
In YNAB, assign all the transactions you want to be split to your "to split" category that you specified in the config file. Close YNAB and give Dropbox a few seconds to sync. Then, run the script:

```
./ynabsplitter.py
```

Watch the output for any errors. If all goes well, congratulations! You can reopen YNAB and get back to work without having to robotically split transactions.

If you want to export the split information to a spreadsheet and you specified ledgerOutputFormat in the config file, you can now paste into your spreadsheet.

## Credit
The YNAB file formats and cloud sync mechanism are tough to pick up from reverse engineering. I'd like to thank the giants whose shoulders I stood on.
- [Jack Turnbull](https://github.com/jackturnbull), who wrote [a very detailed breakdown of the effects of operations of YNAB files](https://jack.codes/projects/2016/09/13/reversing-the-ynab-file-format-part-1/).
- [Evan Laske](https://github.com/elaske), who wrote [a wiki page on the purposes of fields in .ydevice files](https://github.com/elaske/pynab/wiki/1.1.-Device-Files).
