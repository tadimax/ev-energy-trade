require("@nomicfoundation/hardhat-toolbox");

/** @type import('hardhat/config').HardhatUserConfig */

module.exports = {
  solidity: "0.8.28",
  networks: {
    ganache: {
        url: "http://127.0.0.1:7545",
        chainId: 1337,
        accounts: ["0x3c48a8955d7f2a297d1afeaae62c04519aba5f1ab123114890cb1721e31844a5"]
    }
}
};
