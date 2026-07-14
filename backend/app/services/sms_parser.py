import re
from decimal import Decimal


class SMSParser:


    @staticmethod
    def parse(text: str):

        clean = text.replace(",", "")


        return {

            "source": SMSParser.detect_source(clean),

            "transaction_id":
                SMSParser.extract_transaction_id(clean),

            "amount":
                SMSParser.extract_amount(clean),

        }



    @staticmethod
    def extract_transaction_id(text: str):

        """
        Priority:

        1. Receipt links
        2. Explicit transaction IDs
        3. Transaction number formats

        """


        # ==========================
        # Telebirr receipt
        # ==========================

        match = re.search(
            r"transactioninfo\.ethiotelecom\.et/receipt/([A-Z0-9]+)",
            text,
            re.I
        )

        if match:
            return match.group(1).upper()



        # ==========================
        # CBE receipt
        # Example:
        # cbe.com.et/v2-hfHCxzJmZyrkllKfjzt8
        # ==========================

        match = re.search(
            r"cbe\.com\.et/(?:v2-)?([A-Za-z0-9]+)",
            text,
            re.I
        )

        if match:
            return match.group(1)



        # ==========================
        # BOA receipt
        # ?trx=FT26185DMLVR27413
        # ==========================

        match = re.search(
            r"[?&]trx=([A-Z0-9]+)",
            text,
            re.I
        )

        if match:
            return match.group(1).upper()



        # ==========================
        # Text transaction IDs
        # ==========================

        patterns = [

            # Telebirr
            r"telebirr transaction number is\s+([A-Z0-9]+)",
            r"transaction number is\s+([A-Z0-9]+)",
            r"by transaction number\s+([A-Z0-9]+)",

            # CBE Birr
            r"Txn ID\s+([A-Z0-9]+)",

            # Generic
            r"Transaction ID is\s+([A-Z0-9]+)",
            r"transaction id[:\s]+([A-Z0-9]+)",

        ]


        for pattern in patterns:

            match = re.search(
                pattern,
                text,
                re.I
            )

            if match:

                return match.group(1).upper()



        return None





    @staticmethod
    def detect_source(text):

        lower = text.lower()


        if "telebirr" in lower:

            return "telebirr"



        if "cbe birr" in lower:

            return "cbe_birr"



        if "thanks for banking with cbe" in lower:

            return "cbe"



        if "bank of abyssinia" in lower:

            return "boa"



        return "unknown"





    @staticmethod
    def extract_amount(text: str):

        """
        Used ONLY by Android forwarder.
        The user SMS amount is ignored.
        """


        clean = text.replace(",", "")


        patterns = [

            # Telebirr
            # You have transferred ETB 1000
            r"(?:You have\s+)?(?:received|paid|transferred)\s+ETB\s+([\d.]+)",


            # CBE
            # debit transaction of ETB 300
            r"(?:transaction of|ETB)\s*([\d.]+)",


            # BOA credited/debited
            r"(?:credited with|debited with)\s+ETB\s*([\d.]+)",


            # CBE Birr
            # received 17835.30Br
            r"received\s+([\d.]+)Br",


            # CBE Birr transfer
            r"made\s+([\d.]+)Br\.\s+transfer",

        ]



        for pattern in patterns:


            match = re.search(
                pattern,
                clean,
                re.I
            )


            if match:

                try:

                    return Decimal(
                        match.group(1)
                    )

                except:

                    continue



        return None