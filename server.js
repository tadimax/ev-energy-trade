// server.js
// npm i express cors ethers
const express = require("express");
const cors = require("cors");
const { ethers } = require("ethers");

const app = express();
app.use(cors());
app.use(express.json());

// ⚠️ Station private key (DEMO ONLY). Load from env/secret storage in prod.
const STATION_PK = process.env.STATION_PK || "0xabc123..."; // DO NOT hardcode in real life
const wallet = new ethers.Wallet(STATION_PK);

// EIP-712 domain must match Solidity (name/version), chainId, and contract address
function domain(chainId, contractAddr) {
  return {
    name: "EVEnergy",
    version: "1",
    chainId,
    verifyingContract: contractAddr,
  };
}

const types = {
  SessionStop: [
    { name: "user",        type: "address" },
    { name: "station",     type: "address" },
    { name: "sessionId",   type: "bytes32" },
    { name: "kWhMilli",    type: "uint256" },
    { name: "chainId",     type: "uint256" },
    { name: "contractAddr",type: "address" },
  ],
};

app.post("/sign-stop", async (req, res) => {
  try {
    const { user, station, sessionId, kWhMilli, chainId, contractAddr } = req.body;

    // Basic checks
    if (!ethers.utils.isAddress(user) || !ethers.utils.isAddress(station) || !ethers.utils.isAddress(contractAddr)) {
      return res.status(400).json({ error: "Bad address in payload" });
    }

    // Make sure THIS station is the signer
    if (station.toLowerCase() !== wallet.address.toLowerCase()) {
      return res.status(400).json({ error: "Station address mismatch" });
    }

    const value = { user, station, sessionId, kWhMilli, chainId, contractAddr };
    const sig = await wallet._signTypedData(domain(chainId, contractAddr), types, value);
    res.json({ signature: sig, signer: wallet.address });
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: e.message || "sign failed" });
  }
});

const port = process.env.PORT || 8080;
app.listen(port, () => console.log(`Station signer listening on ${port}`));
