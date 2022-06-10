default: help

help:
	@echo "Use setup.py to build"
	@echo "Extra make targets available:"
	@echo " install-autostart - install autostart files (xdg)"
	@echo " install-icons - install icons"
	@echo " install - calls all of the above (but calling setup.py is still necessary)"

install-icons:
	mkdir -p $(DESTDIR)/usr/share/icons/hicolor/scalable/apps
	cp qubes_new_qube/question_icon.svg $(DESTDIR)/usr/share/icons/hicolor/scalable/apps/qubes-question.svg
	cp qubes_new_qube/question_icon_light.svg $(DESTDIR)/usr/share/icons/hicolor/scalable/apps/qubes-question-light.svg
	cp qubes_new_qube/delete_icon.svg $(DESTDIR)/usr/share/icons/hicolor/scalable/apps/qubes-delete.svg
	cp qubes_new_qube/qubes_logo.svg $(DESTDIR)/usr/share/icons/hicolor/scalable/apps/qubes-logo.svg

install-autostart:
	mkdir -p $(DESTDIR)/etc/xdg/autostart
	mkdir -p $(DESTDIR)/usr/share/applications

install: install-autostart install-icons

.PHONY: clean
clean:
