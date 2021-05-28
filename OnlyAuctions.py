import smartpy as sp


class BatchTransfer:
    def get_transfer_type():
        tx_type = sp.TRecord(to_=sp.TAddress,
                             token_id=sp.TNat,
                             amount=sp.TNat).layout(
            ("to_", ("token_id", "amount"))
        )
        transfer_type = sp.TRecord(from_=sp.TAddress,
                                   txs=sp.TList(tx_type)).layout(
                                       ("from_", "txs"))
        return transfer_type

    def get_type():
        return sp.TList(BatchTransfer.get_transfer_type())

    def item(from_, txs):
        return sp.set_type_expr(sp.record(from_=from_, txs=txs), BatchTransfer.get_transfer_type())


class AuctionErrorMessage:
    PREFIX = "AUC_"
    ID_ALREADY_IN_USE = "{}ID_ALREADY_IN_USE".format(PREFIX)
    SELLER_CANNOT_BID = "{}SELLER_CANNOT_BID".format(PREFIX)
    BID_AMOUNT_TOO_LOW = "{}BID_AMOUNT_TOO_LOW".format(PREFIX)
    AUCTION_IS_OVER = "{}AUCTION_IS_OVER".format(PREFIX)
    AUCTION_IS_ONGOING = "{}AUCTION_IS_ONGOING".format(PREFIX)
    SENDER_NOT_BIDDER = "{}SENDER_NOT_BIDDER".format(PREFIX)
    TOKEN_AMOUNT_TOO_LOW = "{}TOKEN_AMOUNT_TOO_LOW".format(PREFIX)
    END_DATE_TOO_SOON = "{}END_DATE_TOO_SOON".format(PREFIX)
    END_DATE_TOO_LATE = "{}END_DATE_TOO_LATE".format(PREFIX)


INITIAL_BID = sp.mutez(900000)
MINIMAL_BID = sp.mutez(100000)
INITIAL_AUCTION_DURATION = sp.int(24*5)
MINIMAL_AUCTION_DURATION = sp.int(1)
MAXIMAL_AUCTION_DURATION = sp.int(24*7)
MAXIMAL_TOKEN_ID = sp.nat(1689)
# this is the biggest tz3 after this only KT...
THRESHOLD_ADDRESS = sp.address("tz3jfebmewtfXYD1Xef34TwrfMg2rrrw6oum")
DEFAULT_ADDRESS = sp.address("tz1aW9v8Ka7UCuoGFWjzag9Fv599mLbWVSq9")
AUCTION_EXTENSION_THRESHOLD = sp.int(60*5)  # 5 minutes
BID_STEP_THRESHOLD = sp.mutez(100000)


class Auction():
    def get_type():
        return sp.TRecord(token_address=sp.TAddress, token_id=sp.TNat, token_amount=sp.TNat,  end_timestamp=sp.TTimestamp, seller=sp.TAddress, bid_amount=sp.TMutez, bidder=sp.TAddress).layout(("token_address", ("token_id", ("token_amount", ("end_timestamp", ("seller", ("bid_amount", "bidder")))))))


class AuctionCreateRequest():
    def get_type():
        # .layout(("auction_id",("token_address",("token_id",("token_amount",("end_timestamp","bid_amount"))))))
        return sp.TRecord(auction_id=sp.TNat, token_address=sp.TAddress, token_id=sp.TNat, token_amount=sp.TNat,  end_timestamp=sp.TTimestamp,  bid_amount=sp.TMutez)


class UpdateOperatorsRequest():
    def get_operator_param_type():
        return sp.TRecord(
            owner=sp.TAddress,
            operator=sp.TAddress,
            token_id=sp.TNat
        ).layout(("owner", ("operator", "token_id")))

    def get_type():
        return sp.TList(
            sp.TVariant(
                add_operator=UpdateOperatorsRequest.get_operator_param_type(),
                remove_operator=UpdateOperatorsRequest.get_operator_param_type())
        )


class AuctionHouse(sp.Contract):
    def __init__(self):
        self.init(auctions=sp.big_map(tkey=sp.TNat, tvalue=Auction.get_type()))

    @sp.entry_point
    def create_auction(self, create_auction_request):
        sp.set_type_expr(create_auction_request,
                         AuctionCreateRequest.get_type())
        token_contract = sp.contract(BatchTransfer.get_type(
        ), create_auction_request.token_address, entry_point="transfer").open_some()
        sp.verify(create_auction_request.token_amount > 0,
                  message=AuctionErrorMessage.TOKEN_AMOUNT_TOO_LOW)
        sp.verify(create_auction_request.end_timestamp >= sp.now.add_hours(
            MINIMAL_AUCTION_DURATION), message=AuctionErrorMessage.END_DATE_TOO_SOON)
        sp.verify(create_auction_request.end_timestamp <= sp.now.add_hours(
            MAXIMAL_AUCTION_DURATION), message=AuctionErrorMessage.END_DATE_TOO_LATE)
        sp.verify(create_auction_request.bid_amount >= MINIMAL_BID,
                  message=AuctionErrorMessage.BID_AMOUNT_TOO_LOW)
        sp.verify(~self.data.auctions.contains(
            create_auction_request.auction_id), message=AuctionErrorMessage.ID_ALREADY_IN_USE)

        sp.transfer([BatchTransfer.item(sp.sender, [sp.record(to_=sp.self_address, token_id=create_auction_request.token_id,
                                                              amount=create_auction_request.token_amount)])], sp.mutez(0), token_contract)
        self.data.auctions[create_auction_request.auction_id] = sp.record(token_address=create_auction_request.token_address, token_id=create_auction_request.token_id,
                                                                          token_amount=create_auction_request.token_amount, end_timestamp=create_auction_request.end_timestamp, seller=sp.sender, bid_amount=create_auction_request.bid_amount, bidder=sp.sender)

    @sp.entry_point
    def bid(self, auction_id):
        sp.set_type_expr(auction_id, sp.TNat)
        auction = self.data.auctions[auction_id]

        sp.verify(sp.sender != auction.seller,
                  message=AuctionErrorMessage.SELLER_CANNOT_BID)
        sp.verify(sp.amount >= auction.bid_amount+BID_STEP_THRESHOLD,
                  message=AuctionErrorMessage.BID_AMOUNT_TOO_LOW)
        sp.verify(sp.now < auction.end_timestamp,
                  message=AuctionErrorMessage.AUCTION_IS_OVER)

        sp.if auction.bidder != auction.seller:
            sp.if auction.bidder > THRESHOLD_ADDRESS:
                sp.send(DEFAULT_ADDRESS, auction.bid_amount)
            sp.else:
                sp.send(auction.bidder, auction.bid_amount)

        auction.bidder = sp.sender
        auction.bid_amount = sp.amount
        sp.if auction.end_timestamp-sp.now < AUCTION_EXTENSION_THRESHOLD:
            auction.end_timestamp = sp.now.add_seconds(
                AUCTION_EXTENSION_THRESHOLD)
        self.data.auctions[auction_id] = auction

    @sp.entry_point
    def withdraw(self, auction_id):
        sp.set_type_expr(auction_id, sp.TNat)
        auction = self.data.auctions[auction_id]
        sp.verify(sp.now > auction.end_timestamp,
                  message=AuctionErrorMessage.AUCTION_IS_ONGOING)

        token_contract = sp.contract(BatchTransfer.get_type(
        ), auction.token_address, entry_point="transfer").open_some()
        sp.if auction.bidder != auction.seller:
            sp.if auction.seller > THRESHOLD_ADDRESS:
                sp.send(DEFAULT_ADDRESS, auction.bid_amount)
            sp.else:
                sp.send(auction.seller, auction.bid_amount)

        sp.transfer([BatchTransfer.item(sp.self_address, [sp.record(to_=auction.bidder,
                                                                    token_id=auction.token_id, amount=auction.token_amount)])], sp.mutez(0), token_contract)
        del self.data.auctions[auction_id]


if "templates" not in __name__:
    @sp.add_test(name="CricTez Cards NFT")
    def test():
        scenario = sp.test_scenario()
        scenario.h1("CricTez Cards and Marketplace")

        scenario.h1("Auction House")
        auction_house = AuctionHouse()
        scenario += auction_house
