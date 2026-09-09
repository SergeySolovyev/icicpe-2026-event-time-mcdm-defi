import { CreateMarket as CreateMarketEvent } from "../generated/MorphoBlue/MorphoBlue";
import { Market } from "../generated/schema";

/**
 * Единственный хэндлер субграфа.
 *
 * Ни одного eth_call: CreateMarket несёт marketParams целиком в data лога
 * (статический tuple из пяти слов, без offset-слова), а id — в topic1.
 * Любой bind()/try_* здесь превратил бы синк в тысячи RPC-запросов.
 */
export function handleCreateMarket(event: CreateMarketEvent): void {
  let market = new Market(event.params.id);

  let p = event.params.marketParams;
  market.loanToken = p.loanToken;
  market.collateralToken = p.collateralToken;
  market.oracle = p.oracle;
  market.irm = p.irm;
  market.lltv = p.lltv;

  market.blockNumber = event.block.number;
  market.blockTimestamp = event.block.timestamp;
  market.txHash = event.transaction.hash;
  market.creator = event.transaction.from;

  market.save();
}
