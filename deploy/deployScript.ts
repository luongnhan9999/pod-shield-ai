import { readFileSync, existsSync } from "fs";
import path from "path";
import {
  TransactionHash,
  TransactionStatus,
  GenLayerClient,
  DecodedDeployData,
  GenLayerChain,
} from "genlayer-js/types";
import { localnet } from "genlayer-js/chains";

// Simple manual .env parser to avoid extra dependency issues
if (existsSync(".env")) {
  try {
    const envFile = readFileSync(".env", "utf-8");
    for (const line of envFile.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const index = trimmed.indexOf("=");
      if (index !== -1) {
        const key = trimmed.substring(0, index).trim();
        const val = trimmed.substring(index + 1).trim();
        process.env[key] = val;
      }
    }
  } catch (e) {
    console.warn("Could not read .env file:", e);
  }
}

export default async function main(client: GenLayerClient<any>) {
  const filePath = path.resolve(process.cwd(), "contracts/pod_shield.py");

  // Read treasury address from environment or use a mock fallback
  const treasuryAddress = process.env.TREASURY_ADDRESS || "0x0000000000000000000000000000000000000000";

  console.log(`Deploying PodShield contract from: ${filePath}`);
  console.log(`Using Treasury Address: ${treasuryAddress}`);

  try {
    const contractCode = new Uint8Array(readFileSync(filePath));

    await client.initializeConsensusSmartContract();

    const deployTransaction = await client.deployContract({
      code: contractCode,
      args: [treasuryAddress],
    });

    console.log(`Deployment transaction sent, hash: ${deployTransaction}`);

    const receipt = await client.waitForTransactionReceipt({
      hash: deployTransaction as TransactionHash,
      status: TransactionStatus.ACCEPTED,
      retries: 200,
    });

    if (
      receipt.status !== 5 &&
      receipt.status !== 6 &&
      receipt.statusName !== "ACCEPTED" &&
      receipt.statusName !== "FINALIZED"
    ) {
      throw new Error(`Deployment failed. Receipt: ${JSON.stringify(receipt)}`);
    }

    const deployedContractAddress =
      (client.chain as GenLayerChain).id === localnet.id
        ? receipt.data.contract_address
        : (receipt.txDataDecoded as DecodedDeployData)?.contractAddress;

    console.log(`Contract deployed successfully at address: ${deployedContractAddress}`);
  } catch (error) {
    throw new Error(`Error during deployment: ${error}`);
  }
}
