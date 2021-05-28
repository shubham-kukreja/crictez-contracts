import smartpy as sp


class FA2ErrorMessage:
    PREFIX = "FA2_"
    TOKEN_UNDEFINED = "{}TOKEN_UNDEFINED".format(PREFIX)
    INSUFFICIENT_BALANCE = "{}INSUFFICIENT_BALANCE".format(PREFIX)
    NOT_OWNER = "{}NOT_OWNER".format(PREFIX)
    OPERATORS_UNSUPPORTED = "{}OPERATORS_UNSUPPORTED".format(PREFIX)


class CricTezErrorMessage:
    PREFIX = "CricTez_"
    CREATION_LIMIT_EXCEEDED = "{}CREATION_LIMIT_EXCEEDED".format(PREFIX)
    CANT_MINT_SAME_TOKEN_TWICE = "{}CANT_MINT_SAME_TOKEN_TWICE".format(PREFIX)
    CONTRACT_IS_PAUSED = "{}CONTRACT_IS_PAUSED".format(PREFIX)
    MIN_VALUE_SHOULD_BE_MORE_THAN_ZERO = "{}MIN_VALUE_SHOULD_BE_MORE_THAN_ZERO".format(
        PREFIX)
    INCORRECT_PURCHASE_VALUE = "{}INCORRECT_PURCHASE_VALUE".format(PREFIX)


class LedgerKey:
    def get_type():
        return sp.TRecord(owner=sp.TAddress, token_id=sp.TNat).layout(("owner", "token_id"))

    def make(owner, token_id):
        return sp.set_type_expr(sp.record(owner=owner, token_id=token_id), LedgerKey.get_type())


class TokenValue:
    def get_type():
        return sp.TRecord(global_card_id=sp.TNat, player_id=sp.TNat, year=sp.TNat, type=sp.TString, edition_no=sp.TNat, ipfs_string=sp.TString).layout(("global_card_id", ("player_id", ("year", ("type", ("edition_no", ("ipfs_string")))))))


class TokenMetadataValue:
    def get_type():
        return sp.TRecord(
            token_id=sp.TNat,
            token_info=sp.TMap(sp.TString, sp.TBytes)
        ).layout(("token_id", "token_info"))


class marketplace:
    """
    type marketplace = {
        key = nat : {
            seller = address,
            sale_value = mutez
        }
    }
    """

    def get_value_type():
        return sp.TRecord(
            seller=sp.TAddress,
            sale_value=sp.TMutez,
        )

    def get_key_type():
        """ CricTez Token ID """
        return sp.TNat


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


class MultipleIPFSList:
    def get_type():
        return sp.TList(sp.TString)


class BalanceOfRequest:
    def get_response_type():
        return sp.TList(
            sp.TRecord(
                request=LedgerKey.get_type(),
                balance=sp.TNat).layout(("request", "balance")))

    def get_type():
        return sp.TRecord(
            requests=sp.TList(LedgerKey.get_type()),
            callback=sp.TContract(BalanceOfRequest.get_response_type())
        ).layout(("requests", "callback"))


class OperatorParam:
    def get_type():
        t = sp.TRecord(
            owner=sp.TAddress,
            operator=sp.TAddress,
            token_id=sp.TNat
        ).layout(("owner", ("operator", "token_id")))

        return t

    def make(owner, operator, token_id):
        r = sp.record(owner=owner,
                      operator=operator,
                      token_id=token_id)
        return sp.set_type_expr(r, OperatorParam.get_type())


class CricTezCards(sp.Contract):
    def __init__(self, admin, metadata, initial_auction_house_address):
        self.init(
            ledger=sp.big_map(tkey=LedgerKey.get_type(), tvalue=sp.TNat),
            token_metadata=sp.big_map(
                tkey=sp.TNat, tvalue=TokenMetadataValue.get_type()),
            paused=False,
            administrator=admin,
            metadata=metadata,
            all_tokens=sp.set(t=sp.TNat),
            tokens=sp.big_map(tkey=sp.TNat, tvalue=TokenValue.get_type()),
            marketplace=sp.big_map(
                tkey=marketplace.get_key_type(), tvalue=marketplace.get_value_type()),
            initial_auction_house_address=initial_auction_house_address
        )

    def is_administrator(self, sender):
        return sender == self.data.administrator

    @sp.entry_point
    def set_administrator(self, params):
        sp.verify(self.is_administrator(sp.sender),
                  message=FA2ErrorMessage.NOT_OWNER)
        self.data.administrator = params

    def is_paused(self):
        return self.data.paused

    @sp.entry_point
    def set_pause(self, params):
        sp.verify(self.is_administrator(sp.sender),
                  message=FA2ErrorMessage.NOT_OWNER)
        self.data.paused = params

    @sp.entry_point
    def mint(self, params):
        sp.verify(~self.is_paused(), CricTezErrorMessage.CONTRACT_IS_PAUSED)
        sp.verify(self.is_administrator(sp.sender),
                  message=FA2ErrorMessage.NOT_OWNER)
        token_id = sp.len(self.data.all_tokens)
        sp.verify(~ self.data.all_tokens.contains(token_id),
                  message=CricTezErrorMessage.CANT_MINT_SAME_TOKEN_TWICE)
        sp.set_type(params.metadata, sp.TMap(sp.TString, sp.TBytes))
        user = LedgerKey.make(sp.sender, token_id)
        self.data.ledger[user] = 1
        self.data.token_metadata[token_id] = sp.record(
            token_id=token_id, token_info=params.metadata)
        self.data.tokens[token_id] = sp.record(global_card_id=token_id, player_id=params.player_id,
                                               year=params.year, type=params.type, edition_no=params.edition_no, ipfs_string=params.ipfs_string)
        self.data.all_tokens.add(token_id)
        ###########################################################################
        # 1. Token ID -> During Tx
        # 2. Put on Sale Directly
        # 3. Mint Multiple Cards
        ###########################################################################

    @sp.entry_point
    def transfer(self, batch_transfers):
        sp.verify(~self.is_paused(), CricTezErrorMessage.CONTRACT_IS_PAUSED)
        sp.set_type(batch_transfers, BatchTransfer.get_type())
        sp.for transfer in batch_transfers:
            sp.for tx in transfer.txs:
                sp.if (tx.amount > sp.nat(0)):
                    from_user = LedgerKey.make(transfer.from_, tx.token_id)
                    to_user = LedgerKey.make(tx.to_, tx.token_id)
                    sp.verify(self.data.all_tokens.contains(
                        tx.token_id), FA2ErrorMessage.TOKEN_UNDEFINED)
                    sp.verify((self.data.ledger[from_user] >= tx.amount),
                              message=FA2ErrorMessage.INSUFFICIENT_BALANCE)
                    sp.verify((sp.sender == transfer.from_) | (
                        sp.sender == self.data.initial_auction_house_address), message=FA2ErrorMessage.NOT_OWNER)
                    self.data.ledger[from_user] = sp.as_nat(
                        self.data.ledger[from_user] - tx.amount)
                    self.data.ledger[to_user] = self.data.ledger.get(
                        to_user, 0) + tx.amount
                sp.if self.data.marketplace.contains(tx.token_id):
                    del self.data.marketplace[tx.token_id]
        ###########################################################################
        # 1. Ownership Check
        # 2. Admin Can Transfer Anything
        # 3. marketplace se kya relation
        ###########################################################################

    @sp.entry_point
    def list_card_on_marketplace(self, params):
        sp.verify(~self.is_paused(), CricTezErrorMessage.CONTRACT_IS_PAUSED)
        sp.set_type(params.token_id, sp.TNat)
        sp.set_type(params.sale_price, sp.TMutez)
        from_user = LedgerKey.make(sp.sender, params.token_id)
        sp.verify(self.data.all_tokens.contains(
            params.token_id), FA2ErrorMessage.TOKEN_UNDEFINED)
        sp.verify(params.sale_price > sp.mutez(0),
                  CricTezErrorMessage.MIN_VALUE_SHOULD_BE_MORE_THAN_ZERO)
        sp.verify(self.data.ledger.contains(from_user),
                  message=FA2ErrorMessage.NOT_OWNER)
        sp.verify((self.data.ledger.get(from_user, sp.nat(0)) >= 1),
                  message=FA2ErrorMessage.INSUFFICIENT_BALANCE)
        self.data.marketplace[params.token_id] = sp.record(
            seller=sp.sender,
            sale_value=params.sale_price
        )

    @sp.entry_point
    def withdraw_card_from_marketplace(self, params):
        sp.verify(~self.is_paused(), CricTezErrorMessage.CONTRACT_IS_PAUSED)
        sp.set_type(params.token_id, sp.TNat)
        from_user = LedgerKey.make(sp.sender, params.token_id)
        sp.verify(self.data.all_tokens.contains(
            params.token_id), FA2ErrorMessage.TOKEN_UNDEFINED)
        sp.verify(self.data.marketplace.contains(
            params.token_id), FA2ErrorMessage.TOKEN_UNDEFINED)
        sp.verify(self.data.ledger.contains(from_user),
                  message=FA2ErrorMessage.NOT_OWNER)
        sp.verify((self.data.ledger.get(from_user, sp.nat(0)) >= 1),
                  message=FA2ErrorMessage.INSUFFICIENT_BALANCE)
        del self.data.marketplace[params.token_id]

    @sp.entry_point
    def buy_card_from_marketplace(self, params):
        sp.verify(~self.is_paused(), CricTezErrorMessage.CONTRACT_IS_PAUSED)
        sp.set_type(params.token_id, sp.TNat)
        sp.verify(self.data.all_tokens.contains(
            params.token_id), FA2ErrorMessage.TOKEN_UNDEFINED)
        sp.verify(self.data.marketplace.contains(
            params.token_id), FA2ErrorMessage.TOKEN_UNDEFINED)
        sp.verify(self.data.marketplace[params.token_id].sale_value ==
                  sp.amount, CricTezErrorMessage.INCORRECT_PURCHASE_VALUE)
        seller = LedgerKey.make(
            self.data.marketplace[params.token_id].seller, params.token_id)
        buyer = LedgerKey.make(sp.sender, params.token_id)
        self.data.ledger[seller] = sp.as_nat(
            self.data.ledger[seller] - 1)
        self.data.ledger[buyer] = 1
        sp.send(self.data.marketplace[params.token_id].seller, sp.amount)
        del self.data.marketplace[params.token_id]

    @sp.entry_point
    def balance_of(self, balance_of_request):
        sp.verify(~self.is_paused(), CricTezErrorMessage.CONTRACT_IS_PAUSED)
        sp.set_type(balance_of_request, BalanceOfRequest.get_type())
        responses = sp.local("responses", sp.set_type_expr(
            sp.list([]), BalanceOfRequest.get_response_type()))
        sp.for request in balance_of_request.requests:
            responses.value.push(sp.record(request=request, balance=self.data.ledger.get(
                LedgerKey.make(request.owner, request.token_id), 0)))
        sp.transfer(responses.value, sp.mutez(0), balance_of_request.callback)

    @sp.entry_point
    def update_operators(self, params):
        sp.set_type(params, sp.TList(
            sp.TVariant(
                add_operator=OperatorParam.get_type(),
                remove_operator=OperatorParam.get_type())))
        sp.failwith(FA2ErrorMessage.OPERATORS_UNSUPPORTED)

    @sp.entry_point
    def intial_auction(self, batch_initial_auction):
        sp.for token_id in batch_initial_auction.token_ids:
            auction_id_runner = sp.local(
                'auction_id_runner', batch_initial_auction.auction_id_start)
            auction_house = sp.contract(AuctionCreateRequest.get_type(
            ), self.data.initial_auction_house_address, entry_point="create_auction").open_some()
            auction_create_request = sp.record(
                auction_id=auction_id_runner.value,
                token_address=sp.self_address,
                token_id=token_id,
                token_amount=sp.nat(1),
                end_timestamp=sp.now.add_hours(INITIAL_AUCTION_DURATION),
                bid_amount=INITIAL_BID
            )
            sp.set_type_expr(auction_create_request,
                             AuctionCreateRequest.get_type())
            sp.transfer(auction_create_request, sp.mutez(0), auction_house)
            auction_id_runner.value += 1


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
    def __init__(self, admin):
        self.init(auctions=sp.big_map(tkey=sp.TNat,
                                      tvalue=Auction.get_type()), admin=admin)

    @sp.entry_point
    def create_auction(self, create_auction_request):
        sp.verify(sp.sender == self.data.admin, FA2ErrorMessage.NOT_OWNER)
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

        scenario.h2("Accounts")
        admin = sp.address("tz1ay5RK1WMQvpfU6HyNHRhvauuJu1ZVwLQy")
        alice = sp.test_account("Alice")
        bob = sp.test_account("Bob")
        dan = sp.test_account("Dan")

        scenario.h1("Auction House")
        auction_house = AuctionHouse(admin)
        scenario += auction_house

        scenario.table_of_contents()

        scenario.show([alice, bob, dan])

        scenario.h2("CricTez NFT Contract")

        c1 = CricTezCards(
            admin=admin,
            metadata=sp.metadata_of_url(
                "https://gist.githubusercontent.com/shubham-kukreja/dfdd7e6f7745acd167173a480d86e92f/"),
            initial_auction_house_address=auction_house.address)

        scenario += c1

        scenario.h2("Initiate initial minting")
        scenario += c1.mint(metadata={'': sp.bytes_of_string('x')}, player_id=0, year=2021, type="Standard",
                            edition_no=1, ipfs_string="ipfs://QmVdbn8QvAADa5ydnqn4dwRdixJiaCHgrWhrxsZ56ZK2vY").run(sender=admin)
        scenario += c1.mint(metadata={'': sp.bytes_of_string('z')}, player_id=0, year=2021, type="Standard",
                            edition_no=2, ipfs_string="ipfs://QmVdbn8QvAADa5ydnqn4dwRdixJiaCHgrWhrxsZ56ZK2vY").run(sender=admin)
        scenario += c1.mint(metadata={'': sp.bytes_of_string('q')}, player_id=0, year=2021, type="Standard",
                            edition_no=3, ipfs_string="ipfs://QmVdbn8QvAADa5ydnqn4dwRdixJiaCHgrWhrxsZ56ZK2vY").run(sender=admin)
        scenario += c1.mint(metadata={'': sp.bytes_of_string('w')}, player_id=0, year=2021, type="Standard",
                            edition_no=4, ipfs_string="ipfs://QmVdbn8QvAADa5ydnqn4dwRdixJiaCHgrWhrxsZ56ZK2vY").run(sender=admin)
        scenario += c1.mint(metadata={'': sp.bytes_of_string('e')}, player_id=0, year=2021, type="Standard",
                            edition_no=5, ipfs_string="ipfs://QmVdbn8QvAADa5ydnqn4dwRdixJiaCHgrWhrxsZ56ZK2vY").run(sender=admin)

        scenario += c1.transfer([BatchTransfer.item(
            admin, [sp.record(to_=alice.address, token_id=0, amount=1)])]).run(sender=admin)
        scenario += c1.transfer([BatchTransfer.item(
            admin, [sp.record(to_=alice.address, token_id=1, amount=1)])]).run(sender=admin)
        scenario += c1.transfer([BatchTransfer.item(
            admin, [sp.record(to_=alice.address, token_id=2, amount=1)])]).run(sender=admin)
        scenario += c1.transfer([BatchTransfer.item(
            admin, [sp.record(to_=alice.address, token_id=3, amount=1)])]).run(sender=admin)
        scenario += c1.transfer([BatchTransfer.item(
            admin, [sp.record(to_=alice.address, token_id=4, amount=1)])]).run(sender=admin)

        scenario.h2("marketplace NFT for sale")
        scenario += c1.list_card_on_marketplace(
            token_id=10, sale_price=sp.mutez(100)).run(sender=alice, valid=False)
        scenario += c1.list_card_on_marketplace(
            token_id=1, sale_price=sp.mutez(100)).run(sender=alice)

        scenario += c1.transfer([BatchTransfer.item(alice.address, [sp.record(
            to_=bob.address, token_id=1, amount=1)])]).run(sender=bob, valid=False)
        scenario += c1.transfer([BatchTransfer.item(alice.address, [sp.record(
            to_=bob.address, token_id=1, amount=1)])]).run(sender=admin, valid=False)
        scenario += c1.transfer([BatchTransfer.item(alice.address, [sp.record(
            to_=bob.address, token_id=1, amount=1)])]).run(sender=alice)

        scenario += c1.list_card_on_marketplace(
            token_id=1, sale_price=sp.mutez(100)).run(sender=bob)
        scenario += c1.list_card_on_marketplace(
            token_id=1, sale_price=sp.mutez(100)).run(sender=alice, valid=False)

        scenario.h2("Purchase NFT")
        scenario += c1.buy_card_from_marketplace(token_id=10).run(
            sender=alice, amount=sp.mutez(10), valid=False)
        scenario += c1.buy_card_from_marketplace(token_id=1).run(
            sender=alice, amount=sp.mutez(10), valid=False)
        scenario += c1.buy_card_from_marketplace(
            token_id=1).run(sender=alice, amount=sp.mutez(100))

        scenario.h2("Withdraw NFT from sale")
        scenario += c1.list_card_on_marketplace(
            token_id=2, sale_price=sp.mutez(100)).run(sender=alice)
        scenario += c1.withdraw_card_from_marketplace(
            token_id=2).run(sender=bob, valid=False)
        scenario += c1.withdraw_card_from_marketplace(
            token_id=1).run(sender=bob, valid=False)
        scenario += c1.withdraw_card_from_marketplace(
            token_id=2).run(sender=alice)

        scenario.h2("Pause the contract")
        scenario += c1.set_pause(True).run(sender=alice, valid=False)
        scenario += c1.set_pause(True).run(sender=admin)

        scenario += c1.mint(metadata={'': sp.bytes_of_string('xyz')}, player_id=0, year=2021, type="Standard", edition_no=5,
                            ipfs_string="ipfs://QmVdbn8QvAADa5ydnqn4dwRdixJiaCHgrWhrxsZ56ZK2vY").run(sender=admin, valid=False)
        scenario += c1.list_card_on_marketplace(
            token_id=3, sale_price=sp.mutez(1000)).run(sender=alice, valid=False)
        scenario += c1.withdraw_card_from_marketplace(
            token_id=3).run(sender=alice, valid=False)
        scenario += c1.buy_card_from_marketplace(token_id=3).run(
            sender=alice, amount=sp.mutez(10), valid=False)
        scenario += c1.transfer([BatchTransfer.item(alice.address, [sp.record(
            to_=bob.address, token_id=1, amount=1)])]).run(sender=bob, valid=False)

        scenario.h2("Un Pause the contract")
        scenario += c1.set_pause(False).run(sender=alice, valid=False)
        scenario += c1.set_pause(False).run(sender=admin)

        scenario.p("Alice Transfer Token ID 1 to Bob")
        scenario += c1.transfer([BatchTransfer.item(alice.address,
                                                    [sp.record(to_=admin, token_id=1, amount=1)])]).run(sender=alice)

        auction_id = sp.nat(0)
        scenario.p("Admin creates Auction")
        scenario += auction_house.create_auction(sp.record(auction_id=auction_id, token_address=c1.address, token_id=sp.nat(
            1), token_amount=sp.nat(1),  end_timestamp=sp.timestamp(60*60),  bid_amount=sp.mutez(100000))).run(sender=admin, now=sp.timestamp(0))

        scenario.p("Bob tries to withdraw")
        scenario += auction_house.withdraw(0).run(sender=bob,
                                                  amount=sp.mutez(0), now=sp.timestamp(0), valid=False)
        scenario.p("Alice bids")
        scenario += auction_house.bid(0).run(sender=alice,
                                             amount=sp.mutez(200000), now=sp.timestamp(0))
        scenario.p("Dan bids")
        scenario += auction_house.bid(0).run(sender=dan,
                                             amount=sp.mutez(300000), now=sp.timestamp(1))
        scenario.p("Alice rebids")
        scenario += auction_house.bid(0).run(sender=alice,
                                             amount=sp.mutez(400000), now=sp.timestamp(2))
        scenario.p("Bob tries to withdraw")
        scenario += auction_house.withdraw(0).run(sender=bob,
                                                  amount=sp.mutez(0), now=sp.timestamp(60*60), valid=False)
        scenario.p("Dan bids")
        scenario += auction_house.bid(0).run(sender=dan,
                                             amount=sp.mutez(500000), now=sp.timestamp(60*60-5))
        scenario.p("Alice rebids")
        scenario += auction_house.bid(0).run(sender=alice,
                                             amount=sp.mutez(600000), now=sp.timestamp(60*60+5*60-6))
        scenario.p("Bob withdraws")
        scenario += auction_house.withdraw(0).run(sender=bob,
                                                  amount=sp.mutez(0), now=sp.timestamp(60*60+5*60-6+5*60+1))
