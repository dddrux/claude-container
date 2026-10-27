// Sincronizacao de nick: WELCOME com o nome final, NP_ROSTER, /nick em rede (host e convidado). Handshake UDP real em loopback.
#include <unistd.h>
#define main game_main
#include "../src/main.cpp"
#undef main
void* SDL_GL_GetProcAddress(const char*) { return nullptr; }
static Uint32 gFakeT = 1000;
Uint32 SDL_GetTicks() { return gFakeT; }
static int fails = 0, checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) { ++fails; printf("  FALHOU linha %d: %s\n", __LINE__, #c); } } while (0)
static int udp() { const int s = (int)socket(AF_INET, SOCK_DGRAM, 0); netSockNonBlock(s); return s; }
static int recvWait(int s, uint8_t* b, int n, int ms = 200) { for (int i = 0; i < ms; i++) { int r = (int)recvfrom(s, (char*)b, n, 0, nullptr, nullptr); if (r > 0) return r; usleep(1000); } return -1; }
static void pump() { for (int i = 0; i < 4; i++) { gFakeT += 20; netPoll(gFakeT); usleep(1500); } }
static void drain(int s) { uint8_t t[512]; while (recvfrom(s, (char*)t, sizeof t, 0, nullptr, nullptr) > 0) {} }
static bool getType(int s, int type, uint8_t* b) { for (int k = 0; k < 20; k++) { if (recvWait(s, b, 512) < 1) return false; if (b[0] == type) return true; } return false; }
static void send2(int s, int type, int sender, const std::string& nm, const uint8_t* pre = nullptr, int npre = 0) {
    sockaddr_in hg{}; hg.sin_family = AF_INET; hg.sin_addr.s_addr = htonl(INADDR_LOOPBACK); hg.sin_port = htons(47931);
    NBuf h; h.put<uint8_t>((uint8_t)type); h.put<uint8_t>((uint8_t)sender); for (int i = 0; i < npre; i++) h.put<uint8_t>(pre[i]);
    h.put<uint8_t>((uint8_t)nm.size()); for (char c : nm) h.put<uint8_t>((uint8_t)c);
    sendto(s, (const char*)h.d, h.n, 0, (sockaddr*)&hg, sizeof hg); pump();
}
static void hello(int s, const std::string& nm) { const uint8_t pre[3] = {(uint8_t)NET_VER, 0, 0}; send2(s, NP_HELLO, 255, nm, pre + 0, 2); }
static std::string str(const uint8_t* b, int& o) { const int l = b[o++]; std::string t((const char*)b + o, (size_t)l); o += l; return t; }
static std::map<int, std::string> roster(uint8_t* b) { std::map<int, std::string> m; int o = 2; const int n = b[o++]; for (int i = 0; i < n; i++) { const int id = b[o++]; m[id] = str(b, o); o += 2; str(b, o); o += 1; } return m; }   // patchFix.15: depois de cada nick: 2 bytes de ping, nome do time (str), 1 byte de plataforma
static void run(const std::string& l) { Phys P{}; execCommand(l, P); }
static std::string last() { return chatLog.empty() ? "" : chatLog.back().s; }
int main() {
    chdir("/tmp"); uint8_t b[512];
    const int G = udp(), H = udp();
    CHECK(netStartHost(47931)); gPlayerName = "Alex"; netOn = true;
    printf("[handshake: convidado com nome padrao ve o nome final]\n");
    hello(G, "Jogador 2");
    CHECK(getType(G, NP_WELCOME, b)); { int o = 28; const std::string host = str(b, o), fin = str(b, o); CHECK(host == "Alex" && fin == "Jogador_2"); }
    CHECK(getType(G, NP_ROSTER, b)); { auto m = roster(b); CHECK(m.size() == 2 && m[0] == "Alex" && m[1] == "Jogador_2"); }
    printf("[segundo convidado: todos recebem a lista nova]\n");
    hello(H, "Zed"); CHECK(getType(H, NP_WELCOME, b)); { int o = 28; str(b, o); CHECK(str(b, o) == "Zed"); }
    CHECK(getType(G, NP_ROSTER, b)); { auto m = roster(b); CHECK(m.size() == 3 && m[2] == "Zed"); }
    printf("[convidado pede /nick (NP_NICKREQ)]\n");
    drain(G); drain(H);
    send2(G, NP_NICKREQ, 1, "Bob"); { bool ok = false; for (auto& p : peers) if (p.id == 1 && p.name == "Bob") ok = true; CHECK(ok); }
    CHECK(getType(H, NP_ROSTER, b)); { auto m = roster(b); CHECK(m[1] == "Bob"); }
    send2(G, NP_NICKREQ, 1, "zed"); CHECK(getType(G, NP_SYS, b)); { int o = 3; CHECK(str(b, o).find("Já existe") != std::string::npos); }
    send2(G, NP_NICKREQ, 1, "a b"); CHECK(getType(G, NP_SYS, b)); { int o = 3; CHECK(str(b, o).find("inválido") != std::string::npos); }
    send2(G, NP_NICKREQ, 1, "alex"); CHECK(getType(G, NP_SYS, b));   // nick do host
    { bool ok = false; for (auto& p : peers) if (p.id == 1 && p.name == "Bob") ok = true; CHECK(ok); }
    printf("[host usa /nick em rede]\n");
    run("/nick zed"); CHECK(last().find("Já existe") == 0 && gPlayerName == "Alex");
    drain(H);
    run("/nick Novo"); CHECK(gPlayerName == "Novo"); CHECK(getType(H, NP_ROSTER, b)); { auto m = roster(b); CHECK(m[0] == "Novo" && m[1] == "Bob"); }
    run("/nick NOVO"); CHECK(gPlayerName == "NOVO");   // so mudar a caixa do proprio nick vale
    printf("[reenvio periodico da lista]\n");
    drain(H); gFakeT += 6000; netUpdate(0.05f); CHECK(getType(H, NP_ROSTER, b)); { auto m = roster(b); CHECK(m[0] == "NOVO"); }
    printf("[convidado: recebe lista, /list, /tell por nome, /nick pedido]\n");
    netStop(); gPlayerName = "ZehLocal"; netOn = true; netHost = false; netSelf = 2; netSock = udp();   // patchFix.15: cada entrada do NP_ROSTER tem ping, time (str vazia) e plataforma; no fim, a contagem de times
    sockaddr_in ha{}; { const int A = udp(); ha.sin_family = AF_INET; ha.sin_addr.s_addr = htonl(INADDR_LOOPBACK); bind(A, (sockaddr*)&ha, sizeof ha); socklen_t al = sizeof ha; getsockname(A, (sockaddr*)&ha, &al); netHostAddr = ha; netConn = true;
    NBuf r = netMk(NP_ROSTER); r.put<uint8_t>(3); r.put<uint8_t>(0); r.put<uint8_t>(4); for (char c : std::string("Host")) r.put<uint8_t>(c); r.put<uint16_t>(0); r.put<uint8_t>(0); r.put<uint8_t>(0);
    r.put<uint8_t>(1); r.put<uint8_t>(4); for (char c : std::string("Alex")) r.put<uint8_t>(c); r.put<uint16_t>(0); r.put<uint8_t>(0); r.put<uint8_t>(0); r.put<uint8_t>(2); r.put<uint8_t>(9); for (char c : std::string("Jogador_1")) r.put<uint8_t>(c); r.put<uint16_t>(0); r.put<uint8_t>(0); r.put<uint8_t>(0);
    r.put<uint8_t>(0); r.d[1] = 0; r.r = 2; netNameRecv(NP_ROSTER, 0, r);
    CHECK(netName() == "Jogador_1" && gPlayerName == "ZehLocal" && netLabel(1) == "Alex" && netLabel(0) == "Host");
    run("/list"); CHECK(last().find("Host") != std::string::npos && last().find("Alex") != std::string::npos);
    run("/tell alex oi"); CHECK(last() == "Você sussurra para Alex: oi");
    run("/nick Zeh"); CHECK(gNickPending == "Zeh" && gPlayerName == "ZehLocal" && last().find("Pedindo") == 0);
    CHECK(recvWait(A, b, sizeof b) > 0 && b[0] == NP_PRIV);   // o /tell
    CHECK(recvWait(A, b, sizeof b) > 0 && b[0] == NP_NICKREQ); { int o = 2; CHECK(str(b, o) == "Zeh"); }
    NBuf r2 = netMk(NP_ROSTER); r2.put<uint8_t>(2); r2.put<uint8_t>(0); r2.put<uint8_t>(4); for (char c : std::string("Host")) r2.put<uint8_t>(c); r2.put<uint16_t>(0); r2.put<uint8_t>(0); r2.put<uint8_t>(0); r2.put<uint8_t>(2); r2.put<uint8_t>(3); for (char c : std::string("Zeh")) r2.put<uint8_t>(c); r2.put<uint16_t>(0); r2.put<uint8_t>(0); r2.put<uint8_t>(0);
    r2.put<uint8_t>(0); r2.r = 2; netNameRecv(NP_ROSTER, 0, r2);
    CHECK(gPlayerName == "Zeh" && netName() == "Zeh" && gNickPending.empty() && netLabel(1) == "Jogador 2");
    { NBuf e = netMk(NP_SYS); e.put<uint8_t>(2); e.put<uint8_t>(3); for (char c : std::string("Err")) e.put<uint8_t>(c); e.r = 2; netNameRecv(NP_SYS, 0, e); CHECK(last() == "Err"); }
    { NBuf e = netMk(NP_SYS); e.put<uint8_t>(2); e.put<uint8_t>(3); for (char c : std::string("Bad")) e.put<uint8_t>(c); e.r = 2; netNameRecv(NP_SYS, 1, e); CHECK(last() == "Err"); }   // so o host manda NP_SYS
    }
    printf("%d verificacoes, %d falhas\n", checks, fails);
    return fails ? 1 : 0;
}
