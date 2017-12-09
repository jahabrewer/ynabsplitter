#!/usr/bin/env python

import json
import os
import re
import uuid
import decimal
import logging
import argparse
import pyperclip
import datetime


# This class tracks tx info to output for a ledger
class TransactionLedger:
    def __init__(self):
        self._txs = []

    def addTx(self, splitAmount, totalAmount, date, memo, payee):
        tx = {
            "splitAmount": splitAmount,
            "totalAmount": totalAmount,
            "txDate": date,
            "memo": memo,
            "date": str(datetime.date.today()),
            "payee": payee
        }
        self._txs.append(tx)

    # Format string should look like "{amount}\t{date}"
    def outputWithFormat(self, format):
        s = ""
        for tx in self._txs:
            line = format
            for key, value in tx.iteritems():
                line = re.sub("\{%s\}" % key, value, line)
            s += line + "\n"
        return s


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            # return float(o)
            return float(o.quantize(decimal.Decimal('.01'), rounding=decimal.ROUND_HALF_EVEN))
        return super(DecimalEncoder, self).default(o)


def dumpJsonDebug(j):
    logging.debug(json.dumps(j, indent=4, cls=DecimalEncoder))


# This class wraps a generator with the ability to peek at the current value.
class EntityVersionIncrementGenerator(object):
    def internalGenerator(self, ev):
        match = re.search("^(?P<prefix>[A-Z]-)(?P<number>\d+)$", ev)
        if not match:
            raise ValueError("Uh oh! Couldn't parse entity version")

        prefix = match.group("prefix")
        number = int(match.group("number"))
        for i in xrange(number + 1, number + 1000):
            yield "%s%d" % (prefix, i)

    def __init__(self, ev):
        self.__gen = self.internalGenerator(ev)
        self.current = ev

    def next(self):
        self.current = next(self.__gen)
        return self.current

    def __call__(self):
        return self


def generateUuid():
    return str(uuid.uuid4()).upper()


def openAndParseJsonFromFile(filePath):
    with open(filePath, "r") as f:
        return json.load(f)


def mapCategoryPathToCategoryId(categoryPath, budgetJson):
    # Parse the master category name and category name from the path
    categoryMatch = re.match("^(?P<masterCategory>[\w\s]+)/(?P<category>[\w\s]+)$", categoryPath)
    if not categoryMatch:
        raise ValueError("Category path must match form \"Master Category Name/Category Name\"")
    masterCategoryName = categoryMatch.group("masterCategory")
    categoryName = categoryMatch.group("category")

    # Look up the mcn and cn in the budget json
    try:
        masterCategoryJson = next(x for x in budgetJson["masterCategories"] if x["name"] == masterCategoryName and (("isTombstone" not in x) or (x["isTombstone"] == False)))
        categoryId = next(x["entityId"] for x in masterCategoryJson["subCategories"] if x["name"] == categoryName and (("isTombstone" not in x) or (x["isTombstone"] == False)))
        return categoryId
    except StopIteration:
        logging.exception("Can't find category named %s" % categoryPath)
        raise


def main():
    # Constants
    splitCategoryId = "Category/__Split__"

    # Parse options
    parser = argparse.ArgumentParser()
    parser.add_argument("-l", "--log", help="log level: debug, info, warning", default="info")
    parser.add_argument("--dryrun", help="don't make any changes", action="store_true")
    parser.add_argument("--config", help="location of the config file (default ./ynabsplitter.json)",
                        default="ynabsplitter.json")
    args = parser.parse_args()
    if args.log:
        numericLevel = getattr(logging, args.log.upper(), None)
        if not isinstance(numericLevel, int):
            raise ValueError('Invalid log level: %s' % args.log)
        logging.basicConfig(level=numericLevel)
    configFileName = args.config

    # Read config settings
    with open(configFileName, "r") as f:
        config = json.load(f)
    ynabDir = config["macYnabDir"] if os.name == "posix" else config["windowsYnabDir"]
    budgetDir = os.path.join(ynabDir, config["budgetName"])
    ymetaFilePath = os.path.join(budgetDir, "Budget.ymeta")
    smallerSplitDenominator = int(config["smallerSplitDenominator"])
    if config["ledgerOutputFormat"] and not re.match("\{\w+\}(\{\w+\}\s+)*", config["ledgerOutputFormat"]):
        raise ValueError("ledgerOutputFormat is invalid")

    # Read the ymeta file to find the budget data dir
    with open(ymetaFilePath, "r") as f:
        ymetaJson = json.load(f)
    relativeDataDirName = ymetaJson["relativeDataFolderName"]
    budgetDataDir = os.path.join(budgetDir, relativeDataDirName)
    logging.info("Budget data dir is %s" % budgetDataDir)

    # Find the device to act as--the longest knowledge string with the highest versions. This method is probably flawed,
    # but it works well enough. Being longest fixes the problem where "A-1" is greater than "A-101,B-3".
    devicesDir = os.path.join(budgetDataDir, "devices")
    filePathsInDevicesDir = [os.path.join(devicesDir, fileName) for fileName in os.listdir(devicesDir)]
    deviceJsons = [openAndParseJsonFromFile(filePath) for filePath in filePathsInDevicesDir if os.path.isfile(filePath)]
    lenOfLongestKnowledge = max([len(x["knowledge"]) for x in deviceJsons])
    deviceJson = max([x for x in deviceJsons if len(x["knowledge"]) == lenOfLongestKnowledge],
                     key=lambda x: x["knowledge"])
    logging.info("Will act as device %s (with knowledge %s)" % (deviceJson["shortDeviceId"], deviceJson["knowledge"]))
    logging.info("Current knowledge is %s" % deviceJson["knowledge"])

    # Set up the entityVersion generator to version new objects
    deviceCurrentEntityVersion = re.search("%s-\d+" % deviceJson["shortDeviceId"], deviceJson["knowledge"]).group()
    logging.info("Current entity version is %s" % deviceCurrentEntityVersion)
    evGen = EntityVersionIncrementGenerator(deviceCurrentEntityVersion)

    # Open the budget file and parse the json
    deviceBudgetDir = os.path.join(budgetDataDir, deviceJson["deviceGUID"])
    budgetFilePath = os.path.join(deviceBudgetDir, "Budget.yfull")
    logging.info("Reading budget from %s" % budgetFilePath)
    with open(budgetFilePath, "r") as f:
        budgetJson = json.load(f, parse_float=decimal.Decimal, parse_int=decimal.Decimal)

    # Map the category names to IDs
    toSplitCategoryId = mapCategoryPathToCategoryId(config["toSplitCategoryPath"], budgetJson)
    smallerSplitCategoryPath = config["smallerSplitCategoryPath"]
    smallerSplitCategoryId = mapCategoryPathToCategoryId(smallerSplitCategoryPath,
                                                         budgetJson) if smallerSplitCategoryPath else None
    largerSplitCategoryPath = config["largerSplitCategoryPath"]
    largerSplitCategoryId = mapCategoryPathToCategoryId(largerSplitCategoryPath,
                                                        budgetJson) if largerSplitCategoryPath else None
    logging.info("\"To Split\" category ID is %s" % toSplitCategoryId)
    logging.info("\"Smaller Split\" category ID is %s" % smallerSplitCategoryId)
    logging.info("\"Larger Split\" category ID is %s" % largerSplitCategoryId)
    # exit(0)

    txsToSplit = [x for x in budgetJson["transactions"] if x["categoryId"] == toSplitCategoryId]
    logging.info("There are %d transactions to split" % len(txsToSplit))

    tl = TransactionLedger()
    txDiffs = []
    for tx in txsToSplit:
        logging.info("Modifying transaction %s on %s for %s" % (tx["entityId"], tx["date"], str(tx["amount"])))

        # If the tx is already split, skip it
        if tx["categoryId"] == splitCategoryId:
            logging.info("Transaction is already split, skipping")
            continue

        # Change the category ID to split
        tx["categoryId"] = splitCategoryId

        # Figure out the split. tx["amount"] is type Decimal!
        smallerSplit = tx["amount"] / smallerSplitDenominator
        largerSplit = tx["amount"] - smallerSplit

        # Look up the payee
        payeeName = next(x["name"] for x in budgetJson["payees"] if x["entityId"] == tx["payeeId"])

        # Add this tx's details to the ledger
        # The abs calls make this only work one way. That's probably fine.
        memo = tx["memo"] if "memo" in tx else ""
        tl.addTx(str(abs(smallerSplit)), str(abs(tx["amount"])), tx["date"], memo, payeeName)

        # Create the subtxs
        smallerSubTxEv = evGen.next()
        largerSubTxEv = evGen.next()
        smallerSubTxEntityId = generateUuid()
        largerSubTxEntityId = generateUuid()
        subTxs = [
            {
                "entityType": "subTransaction",
                "categoryId": smallerSplitCategoryId,
                "amount": smallerSplit,
                "entityVersion": smallerSubTxEv,
                "entityId": smallerSubTxEntityId,
                "parentTransactionId": tx["entityId"]
            },
            {
                "entityType": "subTransaction",
                "categoryId": largerSplitCategoryId,
                "amount": largerSplit,
                "entityVersion": largerSubTxEv,
                "entityId": largerSubTxEntityId,
                "parentTransactionId": tx["entityId"]
            }
        ]
        tx["subTransactions"] = subTxs

        # Update the entity version of the tx
        tx["entityVersion"] = evGen.next()

        # Create the diff entry for this tx
        txDiffs.append({
            "flag": None,
            "importedPayee": None,
            "date": tx["date"],
            "subTransactions": [
                {
                    "targetAccountId": None,
                    "transferTransactionId": None,
                    "categoryId": smallerSplitCategoryId,
                    "entityVersion": smallerSubTxEv,
                    "isTombstone": False,
                    "isResolvedConflict": False,
                    "amount": smallerSplit,
                    "madeWithKnowledge": None,
                    "memo": None,
                    "parentTransactionId": tx["entityId"],
                    "entityId": smallerSubTxEntityId,
                    "entityType": "subTransaction",
                    "checkNumber": None
                },
                {
                    "targetAccountId": None,
                    "transferTransactionId": None,
                    "categoryId": largerSplitCategoryId,
                    "entityVersion": largerSubTxEv,
                    "isTombstone": False,
                    "isResolvedConflict": False,
                    "amount": largerSplit,
                    "madeWithKnowledge": None,
                    "memo": None,
                    "parentTransactionId": tx["entityId"],
                    "entityId": largerSubTxEntityId,
                    "entityType": "subTransaction",
                    "checkNumber": None
                }
            ],
            "matchedTransactions": None,
            "YNABID": None,
            "FITID": None,
            "source": None,
            "entityId": tx["entityId"],
            "entityType": "transaction",
            "targetAccountId": None,
            "transferTransactionId": None,
            "categoryId": splitCategoryId,
            "payeeId": tx["payeeId"],
            "entityVersion": tx["entityVersion"],
            "parentTransactionIdIfMatched": None,
            "isTombstone": False,
            "isResolvedConflict": False,
            "amount": tx["amount"],
            "accountId": tx["accountId"],
            "memo": None,
            "madeWithKnowledge": None,
            "cleared": "Uncleared",
            "dateEnteredFromSchedule": None,
            "accepted": True,
            "checkNumber": None
        })

    finalEntityVersion = evGen.current
    logging.info("Final entity version is %s" % finalEntityVersion)

    # Update the file metadata and commit changes if any modifications were made
    if any(txsToSplit):
        updatedKnowledge = \
            re.sub("%s-\d+" % deviceJson["shortDeviceId"], finalEntityVersion,
                   budgetJson["fileMetaData"]["currentKnowledge"])
        budgetJson["fileMetaData"]["currentKnowledge"] = updatedKnowledge
        logging.info("File metadata knowledge updated to %s" % updatedKnowledge)

        # Put together the tx diffs into the full diff file.
        diff = {
            "deviceGUID": deviceJson["deviceGUID"],
            "shortDeviceId": deviceJson["shortDeviceId"],
            "formatVersion": None,
            "dataVersion": "4.2",
            "startVersion": deviceJson["knowledge"],
            "endVersion": updatedKnowledge,
            "budgetDataGUID": None,
            "items": txDiffs,
            "publishTime": ""
        }

        # Write the diff to the device data folder
        diffFileName = diff["startVersion"]
        diffPath = os.path.join(deviceBudgetDir, diffFileName)
        if args.dryrun:
            logging.info("Skipping diff file write because dry run")
            dumpJsonDebug(diff)
        else:
            logging.info("Writing new diff file to %s" % diffPath)
            with open(diffPath, "w") as f:
                json.dump(diff, f, indent=4, cls=DecimalEncoder)

        # Write updated budget to file
        if args.dryrun:
            logging.info("Skipping budget file write because dry run")
        else:
            logging.info("Writing updated budget to %s" % budgetFilePath)
            with open(budgetFilePath, "w") as f:
                json.dump(budgetJson, f, indent=4, cls=DecimalEncoder)
    else:
        logging.info("Nothing to do!")

    if args.dryrun:
        logging.info("Skipping ledger output copy to clipboard because dry run")
    else:
        if config["ledgerOutputFormat"]:
            logging.info("Copying ledger output to clipboard")
            ledgerOutput = tl.outputWithFormat(config["ledgerOutputFormat"])
            pyperclip.copy(ledgerOutput)


if __name__ == "__main__":
    main()
