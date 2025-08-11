import json
import pathlib
import shutil
import time

from web3 import Web3
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes
import solcx
from solcx import compile_files

# ========= CONFIG =========
TARGET_SOLC = "0.8.20"
GANACHE_RPC = "http://127.0.0.1:7545"

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent
CONTRACTS_DIR = PROJECT_ROOT / "contracts"
# Pick ONE of these depending on what you’re deploying:
#CONTRACT_FILE = CONTRACTS_DIR / "EnergyTrade.sol"          # (no OZ imports)
CONTRACT_FILE = CONTRACTS_DIR / "EVChargingSessions.sol"    # (uses OZ 4.9 imports)
CONTRACT_NAME = "EVChargingSessions"                        # or "EnergyTrade"

NODE_MODULES = PROJECT_ROOT / "node_modules"
FRONTEND_OUT = PROJECT_ROOT / "frontend" / "contract-info.json"

EVM_VERSION = "berlin"      # good for Ganache
GAS_PRICE_GWEI = "50"
GAS_LIMIT = 3_000_000

# ========= SOLC SETUP =========
installed = list(map(str, solcx.get_installed_solc_versions()))
if TARGET_SOLC not in installed:
    print(f"Installing solc {TARGET_SOLC} via solcx...")
    solcx.install_solc(TARGET_SOLC)
solcx.set_solc_version(TARGET_SOLC)

print("Active solc (via solcx):", solcx.get_solc_version())
print("Global solc on PATH:", shutil.which("solc") or "not found")
print("Global solcjs on PATH:", shutil.which("solcjs") or "not found")

# ========= WEB3 SETUP =========
web3 = Web3(Web3.HTTPProvider(GANACHE_RPC))
if not web3.is_connected():
    raise RuntimeError("❌ Failed to connect to Ganache")
print("✅ Connected to Ethereum network")

deployer_addr = web3.eth.accounts[0]  # Ganache unlocked account

# ========= RSA HELPERS =========
def generate_rsa_keys():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()

def encrypt_message(pub, message: bytes) -> bytes:
    return pub.encrypt(
        message,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                     algorithm=hashes.SHA256(), label=None)
    )

def decrypt_message(priv, ciphertext: bytes) -> bytes:
    return priv.decrypt(
        ciphertext,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                     algorithm=hashes.SHA256(), label=None)
    )

# ========= COMPILE (with OZ 4.9 remapping) =========
def compile_contract():
    # Remap @openzeppelin -> node_modules/@openzeppelin
    remappings = [f"@openzeppelin/={NODE_MODULES}/@openzeppelin/"]

    compiled = compile_files(
        [str(CONTRACT_FILE)],
        output_values=["abi", "bin"],
        evm_version=EVM_VERSION,
        optimize=True,
        optimize_runs=200,
        import_remappings=remappings,
        allow_paths=[str(NODE_MODULES), str(CONTRACTS_DIR)],
    )

    # key looks like "<path>:<ContractName>"
    key = None
    for k in compiled.keys():
        if k.endswith(f":{CONTRACT_NAME}"):
            key = k
            break
    if not key:
        raise RuntimeError(f"Contract {CONTRACT_NAME} not found in compiled keys: {list(compiled.keys())}")

    art = compiled[key]
    return art["abi"], art["bin"]

# ========= DEPLOY =========
def deploy(abi, bytecode, *ctor_args):
    contract = web3.eth.contract(abi=abi, bytecode=bytecode)
    tx_hash = contract.constructor(*ctor_args).transact({
        "from": deployer_addr,
        "gas": GAS_LIMIT,
        "gasPrice": web3.to_wei(GAS_PRICE_GWEI, "gwei"),
    })
    print(f"⏳ Deploy tx sent: {tx_hash.hex()}")
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"✅ {CONTRACT_NAME} deployed at: {receipt.contractAddress}")
    return web3.eth.contract(address=receipt.contractAddress, abi=abi)

# ========= UTILS =========
def show_contract_balance(addr):
    bal = web3.eth.get_balance(addr)
    print(f"🏦 Contract balance: {web3.from_wei(bal, 'ether')} ETH")

def write_frontend_info(address, abi):
    FRONTEND_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(FRONTEND_OUT, "w", encoding="utf-8") as f:
        json.dump({"address": address, "abi": abi}, f, indent=2)
    print(f"📝 Wrote {FRONTEND_OUT}")

# ========= MAIN =========
if __name__ == "__main__":
    try:
        # 1) RSA keys
        print("\n🔐 Generating RSA key pair...")
        priv, pub = generate_rsa_keys()

        # 2) Compile
        print("\n🧱 Compiling contract...")
        abi, bytecode = compile_contract()

        # 3) Deploy
        print("\n🚀 Deploying contract...")
        if CONTRACT_NAME == "EnergyTrade":
            token_price = web3.to_wei(0.1, "ether")
            energy_batch_hash = f"QmEnergyBatch_{int(time.time())}"
            c = deploy(abi, bytecode, token_price, energy_batch_hash)
        else:
            # EVChargingSessions has no constructor args
            c = deploy(abi, bytecode)

        # 4) Save for frontend
        write_frontend_info(c.address, abi)

        # 5) Demo purchase / start flow
        if CONTRACT_NAME == "EnergyTrade":
            show_contract_balance(c.address)
            print("\n⚡ Buying an energy token...")
            price = c.functions.tokenPrice().call()
            tx_hash = c.functions.buyEnergyToken().transact({
                "from": deployer_addr,
                "value": price,
                "gas": 300_000,
                "gasPrice": web3.to_wei(GAS_PRICE_GWEI, "gwei"),
            })
            print(f"⏳ Purchase tx sent: {tx_hash.hex()}")
            rc = web3.eth.wait_for_transaction_receipt(tx_hash)
            print("✅ Purchase mined! Receipt:")
            print(rc)
            show_contract_balance(c.address)

            print("\n🔐 Encrypting transaction hash as access key...")
            access_key = tx_hash.hex().encode()
            enc = encrypt_message(pub, access_key)
            print(f"🔒 Encrypted access key (first 32 bytes): {enc[:32]}...")

            print("\n🔓 Decrypting transaction hash...")
            dec = decrypt_message(priv, enc)
            print(f"🔑 Decrypted access key: {dec.decode()}")

        else:
            # EVChargingSessions quick sanity: read a public var or set a station if you want
            print("\n✅ EVChargingSessions ready. Use the frontend to start/stop sessions.")
            # Example: just show contract balance 0
            show_contract_balance(c.address)

    except Exception as e:
        print(f"❌ Error: {e}")
