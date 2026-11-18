import asyncio
import os

os.environ["CHESS_WEB_MODE"] = "1"

import pygame
from pygame.locals import K_ESCAPE

from constants.piece_color import COLOR
from logic.stage.game_logic_loop import GameLogicLoop
from network.client import WebSocketGameClient
from network.protocol import build_invite_url, room_code_from_invite_url
from utils.board_coordinates import initialize_board_coordinates
from utils import utils
from utils.gamecontext import GameContext
from utils.logging import log_error
from utils.run_config import resolve_game_seed


_BUTTON_LABELS = (
    "Graj lokalnie",
    "Utwórz pokój",
    "Dołącz z linku",
)


def _browser_window():
    from js import window

    return window


def _game_server_url():
    window = _browser_window()
    value = getattr(window, "CHESS_GAME_SERVER_URL", "")
    return str(value).strip()


def _draw_button(screen, button, label, font, selected=False):
    color = (72, 90, 112) if selected else (28, 31, 39)
    pygame.draw.rect(screen, color, button, border_radius=8)
    pygame.draw.rect(screen, (220, 220, 220), button, 1, border_radius=8)
    rendered = font.render(label, True, (255, 255, 255))
    screen.blit(
        rendered,
        (button.centerx - rendered.get_width() // 2,
         button.centery - rendered.get_height() // 2),
    )


def _menu_buttons(screen):
    width = min(420, screen.get_width() - 48)
    height = 50
    gap = 14
    total_height = len(_BUTTON_LABELS) * height + (len(_BUTTON_LABELS) - 1) * gap
    top = screen.get_height() // 2 - total_height // 2
    left = (screen.get_width() - width) // 2
    return [
        pygame.Rect(left, top + index * (height + gap), width, height)
        for index in range(len(_BUTTON_LABELS))
    ]


def _draw_text(screen, text, font, y, color=(255, 255, 255)):
    rendered = font.render(text, True, color)
    screen.blit(rendered, (screen.get_width() // 2 - rendered.get_width() // 2, y))


def _new_game(screen, seed, player_color=None, action_callback=None):
    return GameLogicLoop(
        screen,
        black_ai=None,
        seed=seed,
        local_player_color=player_color,
        action_callback=action_callback,
    )


def _close_game(game):
    if game is not None:
        game.close()


async def main():
    pygame.init()
    context = GameContext()
    screen = pygame.display.set_mode(
        (context.screen_width, context.screen_height),
        pygame.RESIZABLE | pygame.SCALED,
    )
    _browser_window().chessNetwork.syncViewport()
    pygame.display.set_caption("Chess NEXT - gra sieciowa")
    board_image = pygame.image.load(context.board_src).convert()
    flipped_board_image = pygame.transform.rotate(board_image, 180)
    initialize_board_coordinates(context, board_image)
    active_board_image = board_image
    peer = WebSocketGameClient()
    status = "Wybierz tryb gry"
    invite_url = ""
    room_code = room_code_from_invite_url(
        str(_browser_window().location.href))
    game_server_url = _game_server_url()
    game = None
    local_color = None
    game_seed = None
    pending_messages = []
    running = True
    title_font = pygame.font.SysFont(context.comic_sans_font, 42)
    button_font = pygame.font.SysFont(context.comic_sans_font, 21)
    status_font = pygame.font.SysFont(context.comic_sans_font, 18)
    invite_font = pygame.font.SysFont(context.comic_sans_font, 15)
    buttons = _menu_buttons(screen)

    if room_code is not None:
        if game_server_url:
            peer.start_guest(game_server_url, room_code)
            status = "Dołączanie do pokoju {}".format(room_code)
        else:
            status = "Brak skonfigurowanego serwera gry"

    try:
        while running:
            events = pygame.event.get()
            utils.begin_input_frame(events)
            for event in events:
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == K_ESCAPE:
                    if game is not None:
                        _close_game(game)
                        game = None
                        peer.close()
                        local_color = None
                        room_code = None
                        invite_url = ""
                        pending_messages.clear()
                        status = "Wybierz tryb gry"
                    else:
                        running = False

            for message in peer.poll_events():
                message_type = message["t"]
                if message_type == "room_created":
                    game_seed = int(message["seed"])
                    room_code = message.get("room")
                    invite_url = build_invite_url(
                        str(_browser_window().location.href), room_code)
                    status = "Pokój {} utworzony; wyślij link i czekaj".format(
                        room_code)
                elif message_type == "room_joined":
                    game_seed = int(message["seed"])
                    status = "Dołączono do pokoju {}; uruchamianie gry".format(
                        message.get("room"))
                elif message_type == "player_joined":
                    status = "Drugi gracz dołączył; rozpoczynanie partii"
                elif message_type == "game_started":
                    game_seed = int(message["seed"])
                    local_color = COLOR(message["color"])
                    flipped = local_color is COLOR.BLACK
                    initialize_board_coordinates(
                        context, board_image, flipped=flipped)
                    active_board_image = (
                        flipped_board_image if flipped else board_image)
                    game = _new_game(
                        screen,
                        game_seed,
                        player_color=local_color,
                        action_callback=peer.send_action,
                    )
                    status = "Partia na serwerze; grasz {}".format(
                        local_color.value)
                elif message_type == "action":
                    pending_messages.append(message)
                elif message_type == "peer_disconnected":
                    _close_game(game)
                    game = None
                    room_code = None
                    invite_url = ""
                    local_color = None
                    pending_messages.clear()
                    status = "Przeciwnik rozłączył się; pokój został zamknięty"
                elif message_type == "action_rejected":
                    if game is not None:
                        game.reject_pending_network_action()
                    status = "Serwer odrzucił akcję: {}".format(
                        message.get("reason", "nieznany"))
                elif message_type == "error":
                    status = "Błąd połączenia: {}".format(
                        message.get("reason", "nieznany"))
                    log_error(status)
                elif message_type == "server_disconnected":
                    _close_game(game)
                    game = None
                    local_color = None
                    room_code = None
                    invite_url = ""
                    pending_messages.clear()
                    status = "Utracono połączenie z serwerem gry"
                elif message_type == "invite_copied":
                    status = "Skopiowano link zaproszenia"

            if game is None:
                screen.fill((24, 24, 24))
                _draw_text(
                    screen, "Chess NEXT", title_font, 130, (245, 220, 145))
                for index, (button, label) in enumerate(
                    zip(buttons, _BUTTON_LABELS)
                ):
                    _draw_button(
                        screen,
                        button,
                        label,
                        button_font,
                        utils.left_click_event()
                        and button.collidepoint(utils.get_mouse_event()),
                    )

                if utils.left_click_event():
                    mouse_position = utils.get_mouse_event()
                    if buttons[0].collidepoint(mouse_position):
                        peer.close()
                        local_color = None
                        initialize_board_coordinates(context, board_image)
                        active_board_image = board_image
                        game = _new_game(screen, resolve_game_seed())
                        status = "Gra lokalna dla dwóch graczy"
                        utils.begin_input_frame([])
                    elif buttons[1].collidepoint(mouse_position):
                        if not game_server_url:
                            status = "Brak adresu serwera gry w config.js"
                        else:
                            room_code = None
                            invite_url = ""
                            pending_messages.clear()
                            local_color = None
                            peer.start_host(game_server_url)
                            status = "Tworzenie pokoju..."
                    elif buttons[2].collidepoint(mouse_position):
                        if room_code is None:
                            status = "Otwórz link zaproszenia z kodem pokoju"
                        elif not game_server_url:
                            status = "Brak adresu serwera gry w config.js"
                        else:
                            pending_messages.clear()
                            peer.start_guest(game_server_url, room_code)
                            status = "Dołączanie do pokoju {}".format(room_code)

                _draw_text(
                    screen,
                    status,
                    status_font,
                    buttons[-1].bottom + 28,
                    (215, 215, 215),
                )
                if invite_url:
                    shown_url = invite_url
                    rendered_url = invite_font.render(shown_url, True, (190, 220, 255))
                    if rendered_url.get_width() > screen.get_width() - 48:
                        shown_url = invite_url[:68] + "..."
                    _draw_text(
                        screen,
                        shown_url,
                        invite_font,
                        buttons[-1].bottom + 58,
                        (190, 220, 255),
                    )
                    copy_button = pygame.Rect(
                        screen.get_width() // 2 - 90,
                        buttons[-1].bottom + 84,
                        180,
                        40,
                    )
                    _draw_button(screen, copy_button, "Kopiuj link", button_font)
                    if utils.left_click_event() and copy_button.collidepoint(
                        utils.get_mouse_event()
                    ):
                        _browser_window().chessNetwork.copyInvite(invite_url)
            else:
                screen.fill((0, 0, 0))
                screen.blit(active_board_image, context.board_starting_point)
                while pending_messages and not game.is_action_animation_active:
                    message = pending_messages.pop(0)
                    try:
                        action = peer.receive_action(message)
                        game.apply_authoritative_action(action)
                    except (ValueError, RuntimeError) as error:
                        status = "Odrzucono akcję sieciową: {}".format(error)
                        log_error(status)
                        break
                winner = game.play_turn()
                game.draw_pieces()
                _draw_text(screen, status, status_font, 28, (225, 225, 225))
                if winner is not None:
                    _draw_text(
                        screen,
                        "{} wygrywa!".format(winner.value.capitalize()),
                        title_font,
                        screen.get_height() // 2,
                        (40, 40, 40),
                    )

            pygame.display.flip()
            await asyncio.sleep(0)
    finally:
        _close_game(game)
        peer.close()
        pygame.quit()


asyncio.run(main())
